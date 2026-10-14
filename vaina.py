import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io
import subprocess
import os

try:
    import libsql_experimental as libsql
except ImportError:
    libsql = None
# --- CONFIGURACIÓN DE INTERFAZ Y ESTILOS MINIMALISTAS ---
st.set_page_config(page_title="Punto Yali - ERP", layout="wide")

st.markdown("""
    <style>
    /* Ocultar elementos predeterminados de Streamlit para una vista más limpia */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Espaciado general optimizado */
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 2rem;
    }

    /* Tarjetas y contenedores con diseño minimalista moderno */
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.15);
        padding: 22px;
        background-color: rgba(255, 255, 255, 0.015);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }

    /* Estilo estilizado para los botones */
    .stButton button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    
    /* Métricas con diseño limpio */
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.03);
        padding: 15px;
        border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.1);
    }
    </style>
""", unsafe_allow_html=True)
def sincronizar_con_github_al_guardar():
    """Sube automáticamente el archivo de base de datos actualizado a GitHub"""
    if "GITHUB_TOKEN" in st.secrets and os.path.exists('sistema_negocio.db'):
        try:
            token = st.secrets["GITHUB_TOKEN"]
            repo = st.secrets["GITHUB_REPO"]
            repo_url = f"https://{token}@github.com/{repo}.git"
            
            subprocess.run(["git", "config", "--global", "user.email", "erp@puntoyali.com"], capture_output=True)
            subprocess.run(["git", "config", "--global", "user.name", "Punto Yali Bot"], capture_output=True)
            subprocess.run(["git", "add", "sistema_negocio.db"], capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Actualización automática BD: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"], capture_output=True)
            subprocess.run(["git", "push", repo_url, "HEAD:main"], capture_output=True)
        except Exception:
            pass
# --- CONFIGURACIÓN DE BASE DE DATOS (HÍBRIDA: LOCAL O TURSO) ---
def conectar_db():
    conn = sqlite3.connect('sistema_negocio.db', timeout=10, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
    except Exception:
        pass
    return conn

def parse_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    try:
        s = str(val).strip().replace(',', '.')
        return float(s)
    except ValueError:
        return default

def inicializar_db():
    conn = conectar_db()
    cursor = conn.cursor()
    
    # Tablas principales
    queries = [
        '''CREATE TABLE IF NOT EXISTS cierres_diarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, ganancia_neta REAL,
            efectivo_usd REAL, efectivo_bs REAL, punto_neto REAL,
            pago_movil_transferencia REAL, balance_total_usd REAL
        )''',
        '''CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, categoria TEXT, 
            precio_venta REAL, costo_insumo REAL, porcentaje_ganancia REAL DEFAULT 0,
            aplica_iva INTEGER DEFAULT 0, stock REAL
        )''',
        '''CREATE TABLE IF NOT EXISTS ventas_maestro (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, subtotal REAL, impuesto REAL, 
            total REAL, metodo_pago TEXT, cliente TEXT, monto_efectivo_usd REAL DEFAULT 0,
            monto_efectivo_bs REAL DEFAULT 0, monto_pago_movil REAL DEFAULT 0, monto_punto REAL DEFAULT 0
        )''',
        '''CREATE TABLE IF NOT EXISTS ventas_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER, producto_id INTEGER, 
            cantidad INTEGER, precio_unitario REAL
        )''',
        '''CREATE TABLE IF NOT EXISTS egresos_maestro (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, proveedor TEXT, tipo_gasto TEXT, 
            subtotal REAL, porcentaje_impuesto REAL, monto_impuesto REAL, total REAL,
            origen_fondo TEXT DEFAULT 'Banco Bs.', monto_efectivo_usd REAL DEFAULT 0,
            monto_efectivo_bs REAL DEFAULT 0, monto_bancos_bs REAL DEFAULT 0
        )''',
        '''CREATE TABLE IF NOT EXISTS egresos_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT, egreso_id INTEGER, producto_id INTEGER, 
            cantidad INTEGER, costo_unitario REAL
        )''',
        '''CREATE TABLE IF NOT EXISTS deudas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, monto_total REAL, 
            saldo_pendiente REAL, fecha_origen TEXT, ultima_actualizacion TEXT
        )''',
        '''CREATE TABLE IF NOT EXISTS prestamos_personales (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, persona TEXT, 
            monto REAL, concepto TEXT, estado TEXT DEFAULT 'Pendiente'
        )''',
        '''CREATE TABLE IF NOT EXISTS historial_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER, producto_nombre TEXT, 
            fecha TEXT, stock_anterior REAL, stock_nuevo REAL, motivo TEXT
        )''',
        '''CREATE TABLE IF NOT EXISTS movimientos_capital (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, tipo TEXT, 
            efectivo_usd REAL DEFAULT 0, efectivo_bs REAL DEFAULT 0, 
            bancos_bs REAL DEFAULT 0, concepto TEXT
        )''',
        '''CREATE TABLE IF NOT EXISTS categorias (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE)''',
        '''CREATE TABLE IF NOT EXISTS notas_generales (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, nota TEXT)''',
        '''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)'''
    ]
    
    for q in queries:
        cursor.execute(q)
        
    cursor.execute("SELECT COUNT(*) FROM configuracion WHERE clave = 'tasa_dolar'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO configuracion (clave, valor) VALUES ('tasa_dolar', '880.0')")

    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        cats_iniciales = ["Papelería", "Cigarrillos", "Heladería", "Impresiones y Diseño", "Otros"]
        for c in cats_iniciales:
            cursor.execute("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)", (c,))
            
    conn.commit()

def migracion_segura_db():
    conn = conectar_db()
    cursor = conn.cursor()
    columnas_a_verificar = [
        ("ventas_maestro", "metodo_pago", "TEXT"),
        ("ventas_maestro", "cliente", "TEXT"),
        ("ventas_maestro", "monto_efectivo_usd", "REAL DEFAULT 0"),
        ("ventas_maestro", "monto_efectivo_bs", "REAL DEFAULT 0"),
        ("ventas_maestro", "monto_pago_movil", "REAL DEFAULT 0"),
        ("ventas_maestro", "monto_punto", "REAL DEFAULT 0"),
        ("productos", "unidades_por_caja", "REAL DEFAULT 1"),
        ("productos", "es_cigarrillo", "INTEGER DEFAULT 0"),
        ("productos", "porcentaje_ganancia", "REAL DEFAULT 0"),
        ("productos", "aplica_iva", "INTEGER DEFAULT 0"),
        ("productos", "observaciones", "TEXT DEFAULT ''"),
        ("deudas", "detalles", "TEXT DEFAULT ''"),
        ("movimientos_capital", "efectivo_usd", "REAL DEFAULT 0"),
        ("movimientos_capital", "efectivo_bs", "REAL DEFAULT 0"),
        ("movimientos_capital", "bancos_bs", "REAL DEFAULT 0"),
        ("egresos_maestro", "origen_fondo", "TEXT DEFAULT 'Banco Bs.'"),
        ("egresos_maestro", "monto_efectivo_usd", "REAL DEFAULT 0"),
        ("egresos_maestro", "monto_efectivo_bs", "REAL DEFAULT 0"),
        ("egresos_maestro", "monto_bancos_bs", "REAL DEFAULT 0")
    ]
    for tabla, columna, tipo in columnas_a_verificar:
        try:
            cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
        except Exception:
            pass 
    conn.commit()

def obtener_tasa_actual():
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'tasa_dolar'")
        resultado = cursor.fetchone()
        return float(resultado[0]) if resultado else 880.0
    except Exception:
        return 880.0

def guardar_tasa_actual(nueva_tasa):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('tasa_dolar', ?)", (str(nueva_tasa),))
    conn.commit()

inicializar_db()
migracion_segura_db()

if 'carrito' not in st.session_state:
    st.session_state.carrito = []

# --- PANEL LATERAL PARAMÉTRICO Y LIMPIO ---
st.sidebar.markdown("### 🏛️ Punto Yali")
st.sidebar.caption("Sistema ERP de Gestión Comercial")
st.sidebar.markdown("---")

st.sidebar.subheader("⚙️ Parámetros")
tasa_guardada = obtener_tasa_actual()
tasa_dolar = st.sidebar.number_input("Tasa del Dólar (Bs.)", min_value=1.0, value=tasa_guardada, step=0.10, format="%.2f")

if tasa_dolar != tasa_guardada:
    guardar_tasa_actual(tasa_dolar)

st.sidebar.markdown("---")
st.sidebar.subheader("Navegación")
modulo = st.sidebar.radio("Ir al módulo:", [
    "📊 Dashboard / Cierre Caja", 
    "🛒 Registrar Venta (Punto de Venta)", 
    "📦 Inventario y Productos", 
    "📉 Egresos e Impuestos",
    "💰 Finanzas y Capital",
    "👥 Control de Deudores (Fiados)",
    "🛠️ Mantenimiento de Sistema",
    "📜 Historial de Cierres"  
], label_visibility="collapsed")

conn = conectar_db()

# ==========================================
# MÓDULO: MANTENIMIENTO
# ==========================================
if modulo == "🛠️ Mantenimiento de Sistema":
    st.title("🛠️ Mantenimiento del Sistema")
    st.caption("Herramientas de control administrativo y corrección de registros.")
    
    tab_borrado, tab_limpieza = st.tabs(["🎯 Borrado Quirúrgico", "🧹 Reseteo Total"])
    
    with tab_borrado:
        st.subheader("Eliminar Registros Específicos")
        st.write("Selecciona y elimina transacciones erróneas o deudas fantasma de forma directa.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 1️⃣ Venta o Abono")
            df_ventas_err = pd.read_sql_query("SELECT id, fecha, metodo_pago, total, cliente FROM ventas_maestro ORDER BY id DESC LIMIT 20", conn)
            
            if not df_ventas_err.empty:
                st.dataframe(df_ventas_err, use_container_width=True, hide_index=True)
                id_venta_del = st.selectbox("ID de la Venta/Abono a borrar:", df_ventas_err['id'].tolist())
                
                if st.button("🗑️ Borrar Venta Seleccionada", type="primary"):
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM ventas_detalle WHERE venta_id=?", (int(id_venta_del),))
                    cursor.execute("DELETE FROM ventas_maestro WHERE id=?", (int(id_venta_del),))
                    conn.commit()
                    st.success(f"Venta/Abono {id_venta_del} eliminado con éxito.")
                    st.rerun()
            else:
                st.info("No hay ventas registradas recientemente.")
                
        with col2:
            st.markdown("#### 2️⃣ Deuda / Fiado")
            df_deudas_err = pd.read_sql_query("SELECT id, cliente, monto_total, saldo_pendiente FROM deudas ORDER BY id DESC", conn)
            
            if not df_deudas_err.empty:
                st.dataframe(df_deudas_err, use_container_width=True, hide_index=True)
                id_deuda_del = st.selectbox("ID de la Deuda a borrar:", df_deudas_err['id'].tolist())
                
                if st.button("🗑️ Borrar Deuda Seleccionada", type="primary"):
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM deudas WHERE id=?", (int(id_deuda_del),))
                    conn.commit()
                    st.success(f"Deuda {id_deuda_del} eliminada del registro.")
                    st.rerun()
            else:
                st.info("No hay deudas registradas actualmente.")

    with tab_limpieza:
        st.warning("⚠️ **¡Atención!** Esta sección borra todos los movimientos financieros, ventas, egresos y deudas de golpe. El inventario de productos se mantiene intacto.")
        confirmar_limpieza = st.checkbox("Entiendo las consecuencias y deseo borrar TODOS los movimientos financieros permanentemente.")
        
        if st.button("🚨 BORRAR MOVIMIENTOS FINANCIEROS", disabled=not confirmar_limpieza, type="primary"):
            cursor = conn.cursor()
            tablas_a_limpiar = [
                'ventas_maestro', 'ventas_detalle', 'egresos_maestro', 
                'egresos_detalle', 'deudas', 'historial_inventario', 'notas_generales', 'cierres_diarios', 'movimientos_capital', 'prestamos_personales'
            ]
            for tabla in tablas_a_limpiar:
                try:
                    cursor.execute(f"DELETE FROM {tabla}")
                except Exception:
                    pass
            conn.commit()
            st.success("✅ Sistema limpiado por completo.")
            st.balloons()

# ==========================================
# MÓDULO: INVENTARIO (CON PAGINACIÓN Y MÁXIMA VELOCIDAD)
# ==========================================
elif modulo == "📦 Inventario y Productos":
    st.title("📦 Centro de Control de Inventario")
    st.caption("Gestión ágil de existencias, precios y creación de artículos.")
    
    tab_inv, tab_nuevo, tab_cat, tab_pizarra, tab_hist = st.tabs([
        "📋 Existencias y Edición Rápida", "➕ Nuevo Producto", "📁 Categorías", "📝 Pizarra", "📜 Auditoría"
    ])
    
    lista_cats_db = pd.read_sql_query("SELECT nombre FROM categorias", conn)['nombre'].tolist()
    
    with tab_inv:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            cat_filtro = st.selectbox("🔍 Filtrar por Categoría:", ["Todas las Categorías"] + lista_cats_db)
        with col_f2:
            busq_texto = st.text_input("🔎 Buscar producto en tiempo real:", placeholder="Escribe el nombre del artículo...")
        
        query_inv = "SELECT * FROM productos WHERE 1=1"
        params_inv = []
        if cat_filtro != "Todas las Categorías":
            query_inv += " AND categoria = ?"
            params_inv.append(cat_filtro)
        if busq_texto:
            query_inv += " AND nombre LIKE ?"
            params_inv.append(f"%{busq_texto}%")
            
        df_prod = pd.read_sql_query(query_inv, conn, params=tuple(params_inv))
            
        st.markdown("---")
        
        if not df_prod.empty:
            ITEMS_POR_PAGINA = 10
            total_productos = len(df_prod)
            paginas_totales = (total_productos - 1) // ITEMS_POR_PAGINA + 1
            
            col_pg1, col_pg2 = st.columns([2, 4])
            with col_pg1:
                if paginas_totales > 1:
                    pagina_actual = st.selectbox("📄 Página:", range(1, paginas_totales + 1), format_func=lambda x: f"Página {x} de {paginas_totales}")
                else:
                    pagina_actual = 1
            with col_pg2:
                st.caption(f"💡 Mostrando productos {(pagina_actual-1)*ITEMS_POR_PAGINA + 1} al {min(pagina_actual*ITEMS_POR_PAGINA, total_productos)} de {total_productos} encontrados.")
            
            inicio = (pagina_actual - 1) * ITEMS_POR_PAGINA
            fin = inicio + ITEMS_POR_PAGINA
            df_pagina = df_prod.iloc[inicio:fin]
            
            for _, prod in df_pagina.iterrows():
                p_id = int(prod['id'])
                p_nombre = prod['nombre']
                p_cat = prod['categoria']
                p_costo = float(prod['costo_insumo'])
                p_ganancia = float(prod.get('porcentaje_ganancia', 40.0))
                p_iva = int(prod.get('aplica_iva', 0)) == 1
                p_stock = float(prod['stock'])
                p_precio = float(prod['precio_venta'])
                p_obs = str(prod['observaciones'] or '')
                p_es_cig = int(prod.get('es_cigarrillo', 0)) == 1
                p_u_caja = float(prod.get('unidades_por_caja', 1.0))
                
                estado_txt = "🔴 Crítico" if p_stock <= 3 else ("🟡 Bajo" if p_stock <= 10 else "🟢 Normal")
                
                info_extra_str = ""
                if p_es_cig and p_u_caja > 0:
                    p_unit_suelto = p_precio / p_u_caja
                    info_extra_str = f" | 🚬 Suelto: **${p_unit_suelto:.3f}** ({int(p_u_caja)} U/caja)"
                
                with st.expander(f"📦 **{p_nombre}**  |  Categoría: *{p_cat}*  |  Stock: **{p_stock:.1f} U** ({estado_txt})  |  Precio Caja: **${p_precio:.2f}**{info_extra_str}"):
                    with st.form(f"form_edit_{p_id}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            e_nombre = st.text_input("Nombre del Artículo", value=p_nombre, key=f"nom_{p_id}")
                            e_cat = st.selectbox("Categoría", lista_cats_db, index=lista_cats_db.index(p_cat) if p_cat in lista_cats_db else 0, key=f"cat_{p_id}")
                            
                            e_costo_str = st.text_input("Costo Base ($)", value=str(p_costo), key=f"costo_{p_id}")
                            e_ganancia_str = st.text_input("Porcentaje de Ganancia (%)", value=str(p_ganancia), key=f"gan_{p_id}")
                            e_iva = st.checkbox("🏛️ ¿Aplica IVA (16%)?", value=p_iva, key=f"iva_{p_id}")
                            
                            e_costo = parse_float(e_costo_str, p_costo)
                            e_ganancia = parse_float(e_ganancia_str, p_ganancia)
                            
                            m_dec = e_ganancia / 100
                            div = 1.0 - m_dec if m_dec < 1.0 else 0.01
                            p_sin_i = e_costo / div if div > 0 else e_costo
                            e_pv = p_sin_i * 1.16 if e_iva else p_sin_i
                            st.info(f"💵 **Precio Venta Calculado:** ${e_pv:.2f}  *(Ref. Bs: {e_pv * tasa_dolar:,.2f})*")
                            
                        with c2:
                            e_stock_str = st.text_input("Stock Actual", value=str(p_stock), key=f"stk_{p_id}")
                            e_motivo = st.text_input("Motivo de ajuste de stock", placeholder="Ej: Conteo físico / Reposición...", key=f"mot_{p_id}")
                            e_es_cig = st.checkbox("📦 Caja cerrada / Detallado (Ej: Cigarros)", value=p_es_cig, key=f"cig_{p_id}")
                            e_u_caja_str = st.text_input("Unidades por caja", value=str(p_u_caja), key=f"ucaj_{p_id}")
                            
                            e_stock = parse_float(e_stock_str, p_stock)
                            e_u_caja = parse_float(e_u_caja_str, p_u_caja)
                            
                            if e_es_cig and e_u_caja > 0:
                                preview_suelto = e_pv / e_u_caja
                                st.caption(f"🚬 Precio por unidad suelta calculado: **${preview_suelto:.3f}**")
                                
                            e_obs = st.text_area("Observaciones", value=p_obs, key=f"obs_{p_id}")
                            
                        col_btn_g, col_btn_d = st.columns(2)
                        guardar_cambio = col_btn_g.form_submit_button("💾 Guardar Cambios de este Artículo", type="primary")
                        
                        if guardar_cambio:
                            cursor = conn.cursor()
                            v_cig = 1 if e_es_cig else 0
                            v_iva = 1 if e_iva else 0
                            
                            cursor.execute("""UPDATE productos SET 
                                nombre=?, categoria=?, precio_venta=?, costo_insumo=?, porcentaje_ganancia=?, aplica_iva=?, stock=?, unidades_por_caja=?, es_cigarrillo=?, observaciones=? 
                                WHERE id=?""",
                                (e_nombre, e_cat, round(e_pv, 2), e_costo, e_ganancia, v_iva, e_stock, e_u_caja, v_cig, e_obs, p_id))
                            
                            if p_stock != e_stock:
                                cursor.execute("INSERT INTO historial_inventario (producto_id, producto_nombre, fecha, stock_anterior, stock_nuevo, motivo) VALUES (?, ?, ?, ?, ?, ?)",
                                               (p_id, e_nombre, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), p_stock, e_stock, e_motivo if e_motivo else "Ajuste rápido"))
                            conn.commit()
                            st.success(f"✔️ Producto '{e_nombre}' actualizado con éxito.")
                            st.rerun()

                    st.markdown("---")
                    confirmar_del = st.checkbox(f"⚠️ Activar opción para eliminar permanentemente '{p_nombre}'", key=f"chk_del_{p_id}")
                    if confirmar_del:
                        if st.button(f"🗑️ ELIMINAR ESTE PRODUCTO", key=f"btn_del_{p_id}", type="primary"):
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM productos WHERE id = ?", (p_id,))
                            cursor.execute("DELETE FROM historial_inventario WHERE producto_id = ?", (p_id,))
                            conn.commit()
                            st.error(f"💥 Producto eliminado.")
                            st.rerun()
        else:
            st.info("No se encontraron productos con ese término de búsqueda.")

    with tab_nuevo:
        st.subheader("➕ Registrar Nuevo Producto")
        with st.form("form_nuevo_prod_seguro"):
            col1, col2 = st.columns(2)
            with col1:
                nombre_n = st.text_input("Nombre del Artículo")
                categoria_n = st.selectbox("Categoría", lista_cats_db if lista_cats_db else ["Otros"], key="cat_nuevo")
                
                costo_str_n = st.text_input("Costo Base ($)", value="0.00", key="costo_nuevo")
                ganancia_str_n = st.text_input("Porcentaje de Ganancia (%)", value="40.00", key="gan_nuevo")
                iva_n = st.checkbox("🏛️ ¿Aplica IVA (16%)?", key="iva_nuevo")
                
                costo_n = parse_float(costo_str_n)
                ganancia_n = parse_float(ganancia_str_n, 40.0)
                
                m_dec_n = ganancia_n / 100
                div_n = 1.0 - m_dec_n if m_dec_n < 1.0 else 0.01
                p_sin_iva_n = costo_n / div_n if div_n > 0 else costo_n
                precio_v_n = p_sin_iva_n * 1.16 if iva_n else p_sin_iva_n
                
                st.info(f"💵 **Precio Venta Calculado:** ${precio_v_n:.2f}")

            with col2:
                stock_str_n = st.text_input("Stock Inicial (Unidades sueltas)", value="0", key="stock_nuevo")
                obs_n = st.text_area("Observaciones", placeholder="Detalles o presentación...", key="obs_nuevo")
                
                stock_n = parse_float(stock_str_n)
                
                st.markdown("---")
                es_cig_n = st.checkbox("📦 ¿Se vende detallado y por caja cerrada? (Ej: Cigarros)", key="cig_nuevo")
                u_caja_str_n = st.text_input("Unidades que trae la caja", value="20", key="ucaj_nuevo")
                u_caja_n = parse_float(u_caja_str_n, 20.0)
                
                if es_cig_n and u_caja_n > 0:
                    prev_s = precio_v_n / u_caja_n
                    st.caption(f"🚬 Precio unitario suelta resultante: **${prev_s:.3f}**")
            
            if st.form_submit_button("💾 Guardar Nuevo Producto", type="primary"):
                if nombre_n:
                    try:
                        cursor = conn.cursor()
                        val_cig = 1 if es_cig_n else 0
                        val_iva = 1 if iva_n else 0
                        
                        cursor.execute("""INSERT INTO productos 
                            (nombre, categoria, precio_venta, costo_insumo, porcentaje_ganancia, aplica_iva, stock, unidades_por_caja, es_cigarrillo, observaciones) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (nombre_n, categoria_n, round(precio_v_n, 2), costo_n, ganancia_n, val_iva, stock_n, u_caja_n, val_cig, obs_n))
                        
                        cursor.execute("INSERT INTO historial_inventario (producto_id, producto_nombre, fecha, stock_anterior, stock_nuevo, motivo) VALUES (?, ?, ?, ?, ?, ?)",
                                       (cursor.lastrowid, nombre_n, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0.0, stock_n, "Ingreso Inicial"))
                        conn.commit()
                        st.success("✔️ Producto registrado correctamente.")
                        st.rerun()
                    except Exception:
                        st.error("❌ Ya existe un producto registrado con ese mismo nombre o hubo un error.")
                else:
                    st.warning("⚠️ Debes asignarle un nombre al producto.")

    with tab_cat:
        c_add_cat, c_list_cat = st.columns(2)
        with c_add_cat:
            with st.form("form_cat"):
                nueva_cat = st.text_input("Nueva Categoría")
                if st.form_submit_button("Crear"):
                    if nueva_cat:
                        try:
                            cursor = conn.cursor()
                            cursor.execute("INSERT INTO categorias (nombre) VALUES (?)", (nueva_cat,))
                            conn.commit()
                            st.success("Categoría creada.")
                            st.rerun()
                        except Exception:
                            st.error("Ya existe.")
        with c_list_cat:
            st.markdown("**Categorías Activas:**")
            for cat in lista_cats_db:
                st.markdown(f"- 🏷️ {cat}")

    with tab_pizarra:
        nota_texto = st.text_area("Nuevo recordatorio o nota:", placeholder="Ej: Llamar al proveedor...")
        if st.button("📌 Publicar Nota"):
            if nota_texto:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO notas_generales (fecha, nota) VALUES (?, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), nota_texto))
                conn.commit()
                st.rerun()
        
        st.markdown("---")
        df_notas = pd.read_sql_query("SELECT id, fecha, nota FROM notas_generales ORDER BY id DESC", conn)
        if not df_notas.empty:
            for index, row in df_notas.iterrows():
                with st.container(border=True):
                    st.caption(f"🗓️ {row['fecha']}")
                    st.write(row['nota'])
                    if st.button("🗑️ Borrar", key=f"del_nota_{row['id']}"):
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM notas_generales WHERE id=?", (row['id'],))
                        conn.commit()
                        st.rerun()
        else:
            st.info("Pizarra vacía.")

    with tab_hist:
        df_hist = pd.read_sql_query("SELECT fecha as 'Fecha y Hora', producto_nombre as 'Producto', stock_anterior as 'Stock Anterior', stock_nuevo as 'Nuevo Stock', motivo as 'Justificación' FROM historial_inventario ORDER BY id DESC", conn)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

# ==========================================
# MÓDULO: PUNTO DE VENTA (POS)
# ==========================================
elif modulo == "🛒 Registrar Venta (Punto de Venta)":
    st.title("🛒 Punto de Venta (POS)")
    st.caption("Facturación rápida, carrito interactivo y registro automático en caja y bancos.")
    
    df_prod = pd.read_sql_query("SELECT * FROM productos", conn)
    
    if df_prod.empty:
        st.warning("El inventario está vacío. Agrega productos en la sección de Inventario.")
    else:
        with st.container(border=True):
            c_busq, c_presentacion, c_precio, c_cant, c_add = st.columns([3, 2, 2, 1, 1])
            
            with c_busq:
                prod_nombre = st.selectbox("Producto", df_prod['nombre'].tolist(), label_visibility="collapsed")
                info_p = df_prod[df_prod['nombre'] == prod_nombre].iloc[0]
                stock_actual = float(info_p['stock'])
                es_cigarrillo = int(info_p['es_cigarrillo'] if info_p['es_cigarrillo'] else 0)
                u_caja = float(info_p['unidades_por_caja'] if info_p['unidades_por_caja'] else 1.0)
                
            with c_presentacion:
                if es_cigarrillo == 1:
                    opcion_empaque = st.radio("Empaque", ["Unidad/Suelto", "Caja Cerrada"], horizontal=True, label_visibility="collapsed")
                    if opcion_empaque == "Unidad/Suelto" and u_caja > 0:
                        precio_unit_calc = float(info_p['precio_venta']) / u_caja
                        st.caption(f"Stock: {stock_actual:.1f} U | C/U: ${precio_unit_calc:.3f}")
                    else:
                        st.caption(f"Stock: {stock_actual:.1f} U")
                else:
                    opcion_empaque = "Normal"
                    st.caption(f"Stock: {stock_actual:.1f} U")
                
            with c_precio:
                precio_defecto_usd = float(info_p['precio_venta'])
                if st.checkbox("Precio Manual"):
                    precio_manual_bs = st.number_input("Precio Bs.", min_value=0.0, value=round(precio_defecto_usd * tasa_dolar, 2), label_visibility="collapsed")
                    precio_final = precio_manual_bs / tasa_dolar if tasa_dolar > 0 else 0.0
                else:
                    precio_final = precio_defecto_usd
                    st.text(f"Ref: ${precio_final:.2f}")
                    
            with c_cant:
                cant_vender = st.number_input("Cant.", min_value=1, value=1, step=1, label_visibility="collapsed")
                
            with c_add:
                if st.button("➕", type="primary"):
                    if es_cigarrillo == 1:
                        if opcion_empaque == "Caja Cerrada":
                            factor_stock = u_caja
                            precio_ajustado = precio_final
                            nombre_carrito = prod_nombre
                        else:
                            factor_stock = 1.0
                            precio_ajustado = precio_final / u_caja if u_caja > 0 else precio_final
                            nombre_carrito = f"{prod_nombre} (Suelto)"
                    else:
                        factor_stock = 1.0
                        precio_ajustado = precio_final
                        nombre_carrito = prod_nombre
                        
                    st.session_state.carrito.append({
                        'id': int(info_p['id']), 
                        'nombre': nombre_carrito, 
                        'unidades_stock': cant_vender * factor_stock,
                        'cantidad_pantalla': cant_vender, 
                        'precio_u': precio_ajustado, 
                        'subtotal': cant_vender * precio_ajustado
                    })
                    st.rerun()

        if st.session_state.carrito:
            st.markdown("---")
            st.markdown("### 🛍️ Detalle del Carrito de Compras")
            
            carrito_actualizado = []
            for i, item in enumerate(st.session_state.carrito):
                with st.container(border=True):
                    col_det_info, col_det_cant, col_det_precios, col_det_del = st.columns([3, 2, 3, 1])
                    
                    with col_det_info:
                        st.markdown(f"**{item['nombre']}**")
                        p_u_usd = item['precio_u']
                        p_u_bs = p_u_usd * tasa_dolar
                        st.caption(f"Unitario: ${p_u_usd:.3f} ({p_u_bs:.2f} Bs.)")
                        
                    with col_det_cant:
                        nueva_cant = st.number_input("Cantidad", min_value=1, value=int(item['cantidad_pantalla']), key=f"cant_item_{i}")
                        
                    with col_det_precios:
                        sub_usd = nueva_cant * item['precio_u']
                        sub_bs = sub_usd * tasa_dolar
                        st.markdown(f"**Total Línea:**")
                        st.write(f"${sub_usd:.2f}  *({sub_bs:.2f} Bs.)*")
                        
                    with col_det_del:
                        st.write("")
                        st.write("")
                        eliminar = st.button("🗑️", key=f"del_item_{i}")
                        
                    if not eliminar:
                        factor_unitario = item['unidades_stock'] / item['cantidad_pantalla'] if item['cantidad_pantalla'] > 0 else 1.0
                        item_modificado = item.copy()
                        item_modificado['cantidad_pantalla'] = nueva_cant
                        item_modificado['unidades_stock'] = nueva_cant * factor_unitario
                        item_modificado['subtotal'] = sub_usd
                        carrito_actualizado.append(item_modificado)
            
            st.session_state.carrito = carrito_actualizado
            
            if st.session_state.carrito:
                df_cart_calc = pd.DataFrame(st.session_state.carrito)
                total_usd = df_cart_calc['subtotal'].sum()
                total_bs = total_usd * tasa_dolar
                
                st.markdown("---")
                col_usd, col_bs = st.columns(2)
                col_usd.metric("TOTAL NETO", f"${total_usd:.2f}")
                col_bs.metric("TOTAL EN BOLÍVARES", f"{total_bs:.2f} Bs.")
                
                with st.container(border=True):
                    st.subheader("💳 Cierre Financiero y Vuelto")
                    pago_mixto = st.checkbox("🔀 Pago fraccionado / mixto (Múltiples métodos)")
                    vuelto_usd = 0.0
                    vuelto_bs = 0.0
                    
                    if not pago_mixto:
                        col_m, col_c = st.columns(2)
                        with col_m:
                            metodo_pago = st.selectbox("Método de Pago", ["Efectivo (Divisa/USD)", "Efectivo (Bolívares)", "Pago Móvil / Transferencia", "Punto de Venta (Tarjeta)", "Fiado (Crédito)", "Consumo Interno"])
                        
                        with col_c:
                            if metodo_pago == "Fiado (Crédito)":
                                df_deudores_activos = pd.read_sql_query("SELECT DISTINCT cliente FROM deudas WHERE saldo_pendiente >= 0.01", conn)
                                lista_deudores_activos = df_deudores_activos['cliente'].tolist() if not df_deudores_activos.empty else []
                                
                                opciones_deudor = ["-- Seleccionar deudor existente --", "➕ Registrar Nuevo Deudor"] + lista_deudores_activos
                                sel_deudor_pos = st.selectbox("Seleccionar Deudor", opciones_deudor)
                                
                                if sel_deudor_pos == "➕ Registrar Nuevo Deudor":
                                    cliente_name = st.text_input("Escribe el nombre del nuevo deudor:")
                                elif sel_deudor_pos == "-- Seleccionar deudor existente --":
                                    cliente_name = ""
                                else:
                                    cliente_name = sel_deudor_pos
                            elif metodo_pago == "Punto de Venta (Tarjeta)":
                                cliente_name = st.text_input("Cliente / Referencia Tarjeta")
                            else:
                                cliente_name = ""
                        
                        m_ef_usd = total_usd if metodo_pago == "Efectivo (Divisa/USD)" else 0.0
                        m_ef_bs = total_bs if metodo_pago == "Efectivo (Bolívares)" else 0.0
                        m_pm = total_bs if metodo_pago == "Pago Móvil / Transferencia" else 0.0
                        m_ptv = total_bs * 0.98 if metodo_pago == "Punto de Venta (Tarjeta)" else 0.0
                        
                        if metodo_pago == "Efectivo (Divisa/USD)":
                            monto_recibido_usd = st.number_input("💵 Monto recibido en Efectivo USD ($)", min_value=float(round(total_usd, 2)), value=float(round(total_usd, 2)), format="%.2f")
                            vuelto_usd = round(monto_recibido_usd - total_usd, 2)
                            vuelto_bs = round(vuelto_usd * tasa_dolar, 2)
                            st.info(f"💵 **VUELTO:** ${vuelto_usd:.2f}  *(Equivalente a {vuelto_bs:.2f} Bs.)*")
                            
                        elif metodo_pago == "Efectivo (Bolívares)":
                            monto_recibido_bs = st.number_input("💵 Monto recibido en Efectivo Bs.", min_value=float(round(total_bs, 2)), value=float(round(total_bs, 2)), format="%.2f")
                            vuelto_bs = round(monto_recibido_bs - total_bs, 2)
                            vuelto_usd = round(vuelto_bs / tasa_dolar, 2) if tasa_dolar > 0 else 0.0
                            st.info(f"💵 **VUELTO:** {vuelto_bs:.2f} Bs.  *(Equivalente a ${vuelto_usd:.2f})*")

                        monto_ingreso_caja = total_usd if metodo_pago != "Punto de Venta (Tarjeta)" else total_usd * 0.98
                        if metodo_pago in ["Consumo Interno", "Fiado (Crédito)"]:
                            monto_ingreso_caja = 0.0
                            m_ef_usd = m_ef_bs = m_pm = m_ptv = 0.0
                            
                        metodo_final_str = metodo_pago
                        bloquear_registro = False
                        
                        if metodo_pago == "Fiado (Crédito)" and not cliente_name:
                            st.warning("⚠️ Debes seleccionar un deudor existente o registrar un nuevo deudor.")
                            bloquear_registro = True
                        
                    else:
                        st.caption("Indica cuánto abonó el cliente en cada canal (en su moneda respectiva):")
                        col_p1, col_p2, col_p3 = st.columns(3)
                        
                        with col_p1:
                            p_ef_usd = st.number_input("Efectivo USD ($)", min_value=0.0, value=0.0, format="%.2f", key="mix_ef_usd")
                            p_ef_bs = st.number_input("Efectivo Bs. (Bs.)", min_value=0.0, value=0.0, format="%.2f", key="mix_ef_bs")
                        with col_p2:
                            p_pm = st.number_input("Pago Móvil (Bs.)", min_value=0.0, value=0.0, format="%.2f", key="mix_pm")
                        with col_p3:
                            p_ptv_bruto = st.number_input("Punto Venta (Bs.)", min_value=0.0, value=0.0, format="%.2f", key="mix_ptv")
                        
                        p_ptv_neto = p_ptv_bruto * 0.98
                        
                        suma_parcial_usd = p_ef_usd + (p_ef_bs / tasa_dolar if tasa_dolar > 0 else 0) + (p_pm / tasa_dolar if tasa_dolar > 0 else 0) + (p_ptv_neto / tasa_dolar if tasa_dolar > 0 else 0)
                        diferencia = round(suma_parcial_usd - total_usd, 2)
                        
                        if diferencia < -0.01:
                            restante = abs(diferencia)
                            st.warning(f"⚠️ Faltan por distribuir **${restante:.2f}** ({round(restante * tasa_dolar, 2)} Bs.)")
                            bloquear_registro = True
                        elif diferencia > 0.01:
                            vuelto_usd = diferencia
                            vuelto_bs = round(vuelto_usd * tasa_dolar, 2)
                            st.success(f"✅ VUELTO A DAR: ${vuelto_usd:.2f} ({vuelto_bs:.2f} Bs.)")
                            bloquear_registro = False
                        else:
                            st.success("✅ ¡Montos cuadrados con exactitud!")
                            bloquear_registro = False
                            
                        cliente_name = ""
                        m_ef_usd = p_ef_usd
                        m_ef_bs = p_ef_bs
                        m_pm = p_pm
                        m_ptv = p_ptv_neto
                        
                        monto_ingreso_caja = total_usd if total_usd > 0 else 0.0
                        metodo_final_str = "Pago Mixto"

                    b_can, b_pro = st.columns(2)
                    if b_can.button("🗑️ Cancelar Venta"):
                        st.session_state.carrito = []
                        st.rerun()
                        
                    if b_pro.button("✅ Registrar Venta", type="primary", disabled=bloquear_registro):
                        cursor = conn.cursor()
                        ahora_exacto = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        cursor.execute("""INSERT INTO ventas_maestro 
                            (fecha, subtotal, impuesto, total, metodo_pago, cliente, monto_efectivo_usd, monto_efectivo_bs, monto_pago_movil, monto_punto) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (ahora_exacto, total_usd, 0.0, monto_ingreso_caja, metodo_final_str, cliente_name, m_ef_usd, m_ef_bs, m_pm, m_ptv))
                        venta_id = cursor.lastrowid
                        
                        detalles_compra = ", ".join([f"{item['cantidad_pantalla']}x {item['nombre']}" for item in st.session_state.carrito])
                        
                        for item in st.session_state.carrito:
                            cursor.execute("INSERT INTO ventas_detalle (venta_id, producto_id, cantidad, precio_unitario) VALUES (?, ?, ?, ?)",
                                           (venta_id, item['id'], item['cantidad_pantalla'], item['precio_u']))
                            cursor.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (item['unidades_stock'], item['id']))
                            
                            nombre_item_lower = item['nombre'].lower()
                            if ("impresion" in nombre_item_lower or "impresiones" in nombre_item_lower) and "fotografico" not in nombre_item_lower and "foto" not in nombre_item_lower:
                                cursor.execute("SELECT id FROM productos WHERE nombre = 'Hojas carta'")
                                if cursor.fetchone():
                                    cursor.execute("UPDATE productos SET stock = stock - ? WHERE nombre = ?", (item['unidades_stock'], "Hojas carta"))
                        
                        if not pago_mixto and metodo_pago == "Fiado (Crédito)":
                            cursor.execute("SELECT id, detalles FROM deudas WHERE cliente = ? AND saldo_pendiente >= 0.01", (cliente_name,))
                            deuda_existente = cursor.fetchone()
                            
                            if deuda_existente:
                                nuevos_detalles = f"{deuda_existente[1]} | + {detalles_compra}" if deuda_existente[1] else detalles_compra
                                cursor.execute("UPDATE deudas SET monto_total = monto_total + ?, saldo_pendiente = saldo_pendiente + ?, ultima_actualizacion = ?, detalles = ? WHERE id = ?",
                                               (total_usd, total_usd, ahora_exacto, nuevos_detalles, int(deuda_existente[0])))
                            else:
                                cursor.execute("INSERT INTO deudas (cliente, monto_total, saldo_pendiente, fecha_origen, ultima_actualizacion, detalles) VALUES (?, ?, ?, ?, ?, ?)",
                                               (cliente_name, total_usd, total_usd, ahora_exacto, ahora_exacto, detalles_compra))
                            
                        conn.commit()
                        st.session_state.carrito = []
                        st.success("🎉 ¡Venta procesada con éxito y sumada a caja!")
                        st.rerun()

# ==========================================
# MÓDULO: EGRESOS E IMPUESTOS
# ==========================================
elif modulo == "📉 Egresos e Impuestos":
    st.title("📉 Libro de Egresos e Impuestos")
    st.caption("Control de gastos operativos, tributos y deducción automática de cuentas.")
    
    t1, t2 = st.tabs(["💸 Registrar Egreso", "🏛️ Impuestos Municipales"])
    
    with t1:
        with st.form("form_egresos"):
            tipo = st.selectbox("Tipo de Gasto", ["Compra de Mercancía/Insumos", "Pago de Salarios", "Servicios Públicos", "Seguro de Punto de Venta", "Impuestos Alcaldía"])
            desc = st.text_input("Detalle / Proveedor")
            
            c_m1, c_m2 = st.columns(2)
            moneda_egreso = c_m1.selectbox("Moneda del Gasto", ["Dólares ($)", "Bolívares (Bs.)"])
            monto_eg = c_m2.number_input("Monto", min_value=0.0, format="%.2f")
            
            origen_egreso = st.selectbox("¿De dónde salió el dinero?", ["Efectivo USD", "Efectivo Bs.", "Banco / Cuenta Bs."])
            
            if st.form_submit_button("Registrar Egreso y Descontar", type="primary"):
                if monto_eg <= 0:
                    st.error("❌ El monto debe ser mayor a cero.")
                else:
                    if moneda_egreso == "Dólares ($)":
                        m_usd = monto_eg
                        m_bs = monto_eg * tasa_dolar
                        total_ref_usd = monto_eg
                    else:
                        m_bs = monto_eg
                        m_usd = monto_eg / tasa_dolar if tasa_dolar > 0 else 0
                        total_ref_usd = m_usd
                        
                    ef_usd_reg = m_usd if origen_egreso == "Efectivo USD" else 0.0
                    ef_bs_reg = m_bs if origen_egreso == "Efectivo Bs." else 0.0
                    bancos_reg = m_bs if origen_egreso == "Banco / Cuenta Bs." else 0.0
                    
                    cursor = conn.cursor()
                    cursor.execute("""INSERT INTO egresos_maestro 
                        (fecha, proveedor, tipo_gasto, subtotal, porcentaje_impuesto, monto_impuesto, total, origen_fondo, monto_efectivo_usd, monto_efectivo_bs, monto_bancos_bs) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), desc, tipo, total_ref_usd, 0.0, 0.0, total_ref_usd, origen_egreso, ef_usd_reg, ef_bs_reg, bancos_reg))
                    conn.commit()
                    st.success("✔️ Egreso guardado y descontado de tesorería con éxito.")
                    st.rerun()
                
    with t2:
        st.subheader("Cálculo de Alcaldía (Ganancia Neta)")
        dias_historia = st.number_input("Días hacia atrás para el corte", min_value=1, value=7)
        fecha_corte = (datetime.now() - pd.Timedelta(days=dias_historia)).strftime("%Y-%m-%d")
        
        df_ventas_periodo = pd.read_sql_query(
            "SELECT SUM(total) as t FROM ventas_maestro WHERE fecha >= ? AND metodo_pago NOT IN ('Consumo Interno', 'Fiado (Crédito)')", 
            conn, params=(fecha_corte,)
        )
        ventas_totales_periodo = df_ventas_periodo.iloc[0]['t'] if not df_ventas_periodo.empty and pd.notna(df_ventas_periodo.iloc[0]['t']) else 0.0
        
        df_costos_periodo = pd.read_sql_query("""
            SELECT SUM(vd.cantidad * p.costo_insumo) as costo_t
            FROM ventas_detalle vd
            JOIN productos p ON vd.producto_id = p.id
            JOIN ventas_maestro vm ON vd.venta_id = vm.id
            WHERE vm.fecha >= ? AND vm.metodo_pago NOT IN ('Consumo Interno', 'Fiado (Crédito)')
        """, conn, params=(fecha_corte,))
        costos_totales_periodo = df_costos_periodo.iloc[0]['costo_t'] if not df_costos_periodo.empty and pd.notna(df_costos_periodo.iloc[0]['costo_t']) else 0.0
        
        ganancia_neta_acumulada = ventas_totales_periodo - costos_totales_periodo
        
        col_m1, col_m2 = st.columns(2)
        porcentaje_alcaldia = col_m1.slider("Impuesto Municipal (%)", min_value=1.0, max_value=5.0, value=2.0, step=0.5)
        
        if ganancia_neta_acumulada > 0:
            impuesto_a_pagar = ganancia_neta_acumulada * (porcentaje_alcaldia / 100)
            col_m2.success(f"**Ganancia Neta:** ${ganancia_neta_acumulada:.2f}\n\n**A Pagar Alcaldía:** ${impuesto_a_pagar:.2f}")
        else:
            impuesto_a_pagar = 0.0
            col_m2.warning("Sin ganancias gravables en este período.")
            
        st.markdown("---")
        col_btn1, col_btn2 = st.columns(2)
        
        if col_btn1.button("📌 Registrar Seguro Semanal ($1.00)"):
            cursor = conn.cursor()
            cursor.execute("""INSERT INTO egresos_maestro 
                (fecha, proveedor, tipo_gasto, subtotal, porcentaje_impuesto, monto_impuesto, total, origen_fondo, monto_efectivo_usd, monto_efectivo_bs, monto_bancos_bs) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Seguro de Punto", "Seguro de Punto de Venta", 1.0, 0.0, 0.0, 1.0, "Banco Bs.", 0.0, 0.0, 1.0 * tasa_dolar))
            conn.commit()
            st.rerun()
            
        if col_btn2.button(f"🏛️ Pagar Alcaldía (${impuesto_a_pagar:.2f})", disabled=(impuesto_a_pagar<=0), type="primary"):
            cursor = conn.cursor()
            cursor.execute("""INSERT INTO egresos_maestro 
                (fecha, proveedor, tipo_gasto, subtotal, porcentaje_impuesto, monto_impuesto, total, origen_fondo, monto_efectivo_usd, monto_efectivo_bs, monto_bancos_bs) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Alcaldía (Impuesto sobre Ganancia)", "Impuestos Alcaldía", impuesto_a_pagar, 0.0, 0.0, impuesto_a_pagar, "Banco Bs.", 0.0, 0.0, impuesto_a_pagar * tasa_dolar))
            conn.commit()
            st.rerun()

# ==========================================
# MÓDULO: FINANZAS Y CAPITAL (CON PRÉSTAMOS PERSONALES)
# ==========================================
elif modulo == "💰 Finanzas y Capital":
    st.title("💰 Módulo de Finanzas y Capital")
    st.caption("Tesorería unificada: saldo real alimentado automáticamente por ventas, egresos y abonos.")
    
    PIN_SECRETO = "1234"
    password_input = st.text_input("🔒 Ingresa la contraseña de seguridad para acceder:", type="password")
    
    if password_input != PIN_SECRETO:
        if password_input != "":
            st.error("❌ Contraseña incorrecta.")
        st.warning("⚠️ Debes ingresar la contraseña de seguridad autorizada para ver este módulo.")
        st.stop()
    
    st.success("🔓 Acceso autorizado.")
    st.markdown("---")
    
    df_movs = pd.read_sql_query("SELECT tipo, efectivo_usd, efectivo_bs, bancos_bs FROM movimientos_capital", conn)
    ef_usd_mov = 0.0
    ef_bs_mov = 0.0
    bancos_bs_mov = 0.0
    
    if not df_movs.empty:
        for _, row in df_movs.iterrows():
            f_usd = float(row['efectivo_usd'])
            f_ef_bs = float(row['efectivo_bs'])
            f_bancos = float(row['bancos_bs'])
            if row['tipo'] == 'Inyección de Capital':
                ef_usd_mov += f_usd
                ef_bs_mov += f_ef_bs
                bancos_bs_mov += f_bancos
            else:
                ef_usd_mov -= f_usd
                ef_bs_mov -= f_ef_bs
                bancos_bs_mov -= f_bancos

    df_ventas = pd.read_sql_query("SELECT monto_efectivo_usd, monto_efectivo_bs, monto_pago_movil, monto_punto FROM ventas_maestro WHERE metodo_pago != 'Consumo Interno'", conn)
    ef_usd_ventas = df_ventas['monto_efectivo_usd'].sum() if not df_ventas.empty else 0.0
    ef_bs_ventas = df_ventas['monto_efectivo_bs'].sum() if not df_ventas.empty else 0.0
    bancos_bs_ventas = (df_ventas['monto_pago_movil'] + df_ventas['monto_punto']).sum() if not df_ventas.empty else 0.0

    df_egresos = pd.read_sql_query("SELECT monto_efectivo_usd, monto_efectivo_bs, monto_bancos_bs FROM egresos_maestro", conn)
    ef_usd_egresos = df_egresos['monto_efectivo_usd'].sum() if not df_egresos.empty else 0.0
    ef_bs_egresos = df_egresos['monto_efectivo_bs'].sum() if not df_egresos.empty else 0.0
    bancos_bs_egresos = df_egresos['monto_bancos_bs'].sum() if not df_egresos.empty else 0.0

    acum_ef_usd = ef_usd_mov + ef_usd_ventas - ef_usd_egresos
    acum_ef_bs = ef_bs_mov + ef_bs_ventas - ef_bs_egresos
    acum_bancos_bs = bancos_bs_mov + bancos_bs_ventas - bancos_bs_egresos
                
    st.markdown("### 🏛️ Estado Actual de Tesorería (Saldos Reales)")
    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("💵 Efectivo USD", f"${acum_ef_usd:,.2f}", f"Equiv: {acum_ef_usd * tasa_dolar:,.2f} Bs.")
    col_s2.metric("💵 Efectivo Bolívares", f"{acum_ef_bs:,.2f} Bs.", f"Equiv: ${acum_ef_bs / tasa_dolar if tasa_dolar > 0 else 0:,.2f}")
    col_s3.metric("🏦 Cuentas / Banco / Pago Móvil", f"{acum_bancos_bs:,.2f} Bs.", f"Equiv: ${acum_bancos_bs / tasa_dolar if tasa_dolar > 0 else 0:,.2f}")
    
    st.markdown("---")
    st.subheader("⚡ Registrar Movimiento Extraordinario de Capital")
    
    with st.form("form_mov_capital_separado"):
        tipo_mov = st.selectbox("Tipo de Operación", ["Inyección de Capital", "Retiro de Capital"])
        
        col_mc1, col_mc2, col_mc3 = st.columns(3)
        with col_mc1:
            m_ef_usd = st.number_input("Efectivo USD ($)", min_value=0.0, value=0.0, format="%.2f")
        with col_mc2:
            m_ef_bs = st.number_input("Efectivo Bs. (Bs.)", min_value=0.0, value=0.0, format="%.2f")
        with col_mc3:
            m_bancos_bs = st.number_input("Banco / Cuenta (Bs.)", min_value=0.0, value=0.0, format="%.2f")
            
        concepto_mov = st.text_input("Concepto / Descripción", placeholder="Ej: Gasto personal / Fondo inicial extraordinario...")
        
        if st.form_submit_button("💾 Guardar Movimiento", type="primary"):
            if m_ef_usd <= 0 and m_ef_bs <= 0 and m_bancos_bs <= 0:
                st.error("❌ Debes ingresar al menos un monto mayor a cero.")
            else:
                if tipo_mov == "Retiro de Capital":
                    if m_ef_usd > acum_ef_usd + 0.01:
                        st.warning(f"⚠️ Estás retirando más Efectivo USD (${m_ef_usd:.2f}) del disponible (${acum_ef_usd:.2f}).")
                    if m_ef_bs > acum_ef_bs + 0.01:
                        st.warning(f"⚠️ Estás retirando más Efectivo Bs ({m_ef_bs:,.2f} Bs.) del disponible ({acum_ef_bs:,.2f} Bs.).")
                    if m_bancos_bs > acum_bancos_bs + 0.01:
                        st.warning(f"⚠️ Estás retirando más dinero de Banco ({m_bancos_bs:,.2f} Bs.) del disponible ({acum_bancos_bs:,.2f} Bs.).")
                
                cursor = conn.cursor()
                cursor.execute("""INSERT INTO movimientos_capital 
                    (fecha, tipo, efectivo_usd, efectivo_bs, bancos_bs, concepto) 
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tipo_mov, m_ef_usd, m_ef_bs, m_bancos_bs, concepto_mov if concepto_mov else tipo_mov))
                conn.commit()
                st.success("✔️ Movimiento registrado con éxito.")
                st.rerun()
            
    st.markdown("---")
    st.subheader("📜 Historial de Movimientos Extraordinarios")
    df_hist_movs = pd.read_sql_query("SELECT fecha as 'Fecha y Hora', tipo as 'Operación', efectivo_usd as 'Ef. USD ($)', efectivo_bs as 'Ef. Bs (Bs.)', bancos_bs as 'Bancos Bs (Bs.)', concepto as 'Concepto' FROM movimientos_capital ORDER BY id DESC", conn)
    if not df_hist_movs.empty:
        st.dataframe(df_hist_movs, use_container_width=True, hide_index=True)
    else:
        st.info("No hay movimientos extraordinarios registrados.")

    # ==========================================
    # APARTADO: NOTAS Y PRÉSTAMOS PERSONALES
    # ==========================================
    st.markdown("---")
    st.subheader("📝 Notas y Préstamos Personales (Fuera de Caja)")
    st.caption("Anota aquí dinero prestado de forma personal o recordatorios de dinero fuera del negocio comercial.")
    
    with st.form("form_prestamo_personal"):
        col_pp1, col_pp2 = st.columns(2)
        with col_pp1:
            p_persona = st.text_input("Nombre de la Persona / Motivo")
            p_monto = st.number_input("Monto en Dólares ($)", min_value=0.0, value=0.0, format="%.2f")
        with col_pp2:
            p_concepto = st.text_area("Descripción / Detalles", placeholder="Ej: Préstamo personal, me paga la próxima semana...")
        
        if st.form_submit_button("💾 Guardar Nota Personal", type="primary"):
            if p_persona and p_monto > 0:
                cursor = conn.cursor()
                cursor.execute("""INSERT INTO prestamos_personales (fecha, persona, monto, concepto, estado) VALUES (?, ?, ?, ?, ?)""",
                               (datetime.now().strftime("%Y-%m-%d %H:%M"), p_persona, p_monto, p_concepto, "Pendiente"))
                conn.commit()
                st.success("✔️ Nota personal guardada con éxito.")
                st.rerun()
            else:
                st.warning("⚠️ Debes indicar al menos un nombre/persona y un monto mayor a cero.")
                
    st.markdown("##### 📋 Listado de Préstamos Personales Pendientes")
    df_prestamos = pd.read_sql_query("SELECT id, fecha, persona, monto, concepto FROM prestamos_personales WHERE estado = 'Pendiente' ORDER BY id DESC", conn)
    
    if not df_prestamos.empty:
        for _, row_p in df_prestamos.iterrows():
            p_id = int(row_p['id'])
            p_monto_usd = float(row_p['monto'])
            p_monto_bs = p_monto_usd * tasa_dolar
            
            with st.container(border=True):
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"👤 **{row_p['persona']}** — Monto: **${p_monto_usd:.2f}** *({p_monto_bs:,.2f} Bs.)* | 🗓️ *{row_p['fecha']}*")
                    if row_p['concepto']:
                        st.caption(f"📝 {row_p['concepto']}")
                with col_btn:
                    st.write("")
                    if st.button("✅ Pagado", key=f"pagar_prestamo_{p_id}", type="primary"):
                        cursor = conn.cursor()
                        cursor.execute("UPDATE prestamos_personales SET estado = 'Pagado' WHERE id = ?", (p_id,))
                        conn.commit()
                        st.success("¡Marcado como pagado!")
                        st.rerun()
    else:
        st.info("No hay préstamos personales o notas pendientes.")

# ==========================================
# MÓDULO: DEUDORES (FIADOS)
# ==========================================
elif modulo == "👥 Control de Deudores (Fiados)":
    st.title("👥 Cuentas por Cobrar (Fiados)")
    st.caption("Desglose individual por deudor, cálculo en tiempo real a la tasa del día y procesamiento de abonos.")
    
    df_deudas = pd.read_sql_query("SELECT id, cliente, saldo_pendiente FROM deudas WHERE saldo_pendiente >= 0.01", conn)
    
    if not df_deudas.empty:
        st.info("💡 Haz clic sobre el nombre de cualquier deudor para ver el desglose detallado de los artículos que debe y su valor actualizado a la tasa de hoy.")
        
        for index, row in df_deudas.iterrows():
            cliente_actual = row['cliente']
            saldo_usd = float(row['saldo_pendiente'])
            saldo_bs = saldo_usd * tasa_dolar
            
            with st.expander(f"👤 Deudor: **{cliente_actual}**  |  Deuda Pendiente: **${saldo_usd:.2f}** *({saldo_bs:,.2f} Bs.)*"):
                query_articulos = """
                    SELECT p.nombre, vd.cantidad, vd.precio_unitario, vm.fecha
                    FROM ventas_detalle vd
                    JOIN productos p ON vd.producto_id = p.id
                    JOIN ventas_maestro vm ON vd.venta_id = vm.id
                    WHERE vm.cliente = ? AND vm.metodo_pago = 'Fiado (Crédito)'
                """
                df_articulos = pd.read_sql_query(query_articulos, conn, params=(cliente_actual,))
                
                if not df_articulos.empty:
                    st.markdown("##### 🛒 Detalle de Artículos y Precios a la Tasa del Día:")
                    
                    items_formateados = []
                    for _, art in df_articulos.iterrows():
                        p_u_usd = float(art['precio_unitario'])
                        p_u_bs = p_u_usd * tasa_dolar
                        cant = art['cantidad']
                        sub_usd = cant * p_u_usd
                        sub_bs = sub_usd * tasa_dolar
                        
                        items_formateados.append({
                            "Fecha": art['fecha'],
                            "Artículo": art['nombre'],
                            "Cant.": cant,
                            "Precio Unit. ($)": f"${p_u_usd:.2f}",
                            "Precio Unit. (Bs.)": f"{p_u_bs:,.2f} Bs.",
                            "Subtotal ($)": f"${sub_usd:.2f}",
                            "Subtotal (Bs.)": f"{sub_bs:,.2f} Bs."
                        })
                    
                    df_det_show = pd.DataFrame(items_formateados)
                    st.dataframe(df_det_show, use_container_width=True, hide_index=True)
                else:
                    st.warning("⚠️ No se encontró el desglose exacto de los artículos, pero el saldo pendiente registrado es válido.")

                st.markdown("---")
                st.markdown("##### 💵 Registrar Abono o Pago Total")
                
                col_ab1, col_ab2, col_ab3 = st.columns(3)
                with col_ab1:
                    monto_abono = st.number_input(f"Monto a abonar ($)", min_value=0.01, max_value=saldo_usd, value=saldo_usd, format="%.2f", key=f"abono_{row['id']}")
                    monto_abono_bs = monto_abono * tasa_dolar
                    st.caption(f"Equivalente: {monto_abono_bs:,.2f} Bs.")
                with col_ab2:
                    metodo_pago_abono = st.selectbox("Método de Pago", ["Efectivo (Divisa/USD)", "Efectivo (Bolívares)", "Pago Móvil / Transferencia", "Punto de Venta (Tarjeta)"], key=f"metodo_abono_{row['id']}")
                with col_ab3:
                    st.write("")
                    st.write("")
                    procesar_pago = st.button(f"✅ Procesar Abono", key=f"btn_abono_{row['id']}", type="primary")
                    
                if procesar_pago:
                    cursor = conn.cursor()
                    nuevo_bal = round(saldo_usd - monto_abono, 2)
                    if nuevo_bal < 0.01:
                        nuevo_bal = 0.0
                        
                    ahora_exacto = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    if nuevo_bal == 0.0:
                        cursor.execute("DELETE FROM deudas WHERE id = ?", (int(row['id']),))
                    else:
                        cursor.execute("UPDATE deudas SET saldo_pendiente = ?, ultima_actualizacion = ? WHERE id = ?", (nuevo_bal, ahora_exacto, int(row['id'])))
                    
                    m_ef_usd = monto_abono if metodo_pago_abono == "Efectivo (Divisa/USD)" else 0.0
                    m_ef_bs = (monto_abono * tasa_dolar) if metodo_pago_abono == "Efectivo (Bolívares)" else 0.0
                    m_pm = (monto_abono * tasa_dolar) if metodo_pago_abono == "Pago Móvil / Transferencia" else 0.0
                    m_ptv = (monto_abono * tasa_dolar * 0.98) if metodo_pago_abono == "Punto de Venta (Tarjeta)" else 0.0
                    
                    monto_ingreso_caja = monto_abono if metodo_pago_abono != "Punto de Venta (Tarjeta)" else monto_abono * 0.98
                        
                    metodo_final_maestro = f"Abono - {metodo_pago_abono}"
                    nota_cliente = f"Abono Deuda - {cliente_actual}"
                    
                    cursor.execute("""INSERT INTO ventas_maestro 
                        (fecha, subtotal, impuesto, total, metodo_pago, cliente, monto_efectivo_usd, monto_efectivo_bs, monto_pago_movil, monto_punto) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (ahora_exacto, monto_abono, 0.0, monto_ingreso_caja, metodo_final_maestro, nota_cliente, m_ef_usd, m_ef_bs, m_pm, m_ptv))
                    
                    conn.commit()
                    if nuevo_bal == 0.0:
                        st.success(f"✅ ¡Deuda saldada por completo y dinero ingresado a tesorería!")
                    else:
                        st.success(f"✅ Abono procesado con éxito. Resta por pagar: ${nuevo_bal:.2f}")
                    st.rerun()
    else:
        st.success("🎉 ¡Todos los clientes están al día! No hay deudas pendientes.")

# ==========================================
# MÓDULO: DASHBOARD Y CIERRE
# ==========================================
elif modulo == "📊 Dashboard / Cierre Caja":
    st.title("📊 Panel de Control y Cierre de Caja")
    st.caption("Métricas financieras, rentabilidad neta y arqueo detallado por canales de pago.")
    
    fecha_seleccionada = st.date_input("📅 Operaciones del día:", value=datetime.now(), key="calendario_dashboard")
    hoy = fecha_seleccionada.strftime("%Y-%m-%d")
    param_hoy = f"{hoy}%"
    
    query_ventas = "SELECT * FROM ventas_maestro WHERE fecha LIKE ?"
    query_egresos = "SELECT total FROM egresos_maestro WHERE fecha LIKE ?"
    query_costos = """SELECT SUM(vd.cantidad * p.costo_insumo) as costo_total 
                      FROM ventas_detalle vd 
                      JOIN productos p ON vd.producto_id = p.id 
                      JOIN ventas_maestro vm ON vd.venta_id = vm.id 
                      WHERE vm.fecha LIKE ?"""
    
    df_ventas_hoy = pd.read_sql_query(query_ventas, conn, params=(param_hoy,))
    df_egresos_hoy = pd.read_sql_query(query_egresos, conn, params=(param_hoy,))
    df_costos_hoy = pd.read_sql_query(query_costos, conn, params=(param_hoy,))
    
    if not df_ventas_hoy.empty:
        df_ventas_comerciales = df_ventas_hoy[(~df_ventas_hoy['metodo_pago'].str.startswith('Abono', na=False)) & (df_ventas_hoy['metodo_pago'] != 'Consumo Interno')]
        df_abonos = df_ventas_hoy[df_ventas_hoy['metodo_pago'].str.startswith('Abono', na=False)]
    else:
        df_ventas_comerciales = pd.DataFrame(columns=['subtotal', 'total', 'metodo_pago'])
        df_abonos = pd.DataFrame(columns=['subtotal', 'total', 'metodo_pago'])
        
    valor_mercancia_despachada = df_ventas_comerciales['subtotal'].sum() if not df_ventas_comerciales.empty else 0.0
    costo_mercancia = df_costos_hoy.iloc[0]['costo_total'] if not df_costos_hoy.empty and pd.notna(df_costos_hoy.iloc[0]['costo_total']) else 0.0
    egresos_hoy = df_egresos_hoy['total'].sum() if not df_egresos_hoy.empty else 0.0
    
    comisiones_punto_descontadas = df_ventas_comerciales['subtotal'].sum() - df_ventas_comerciales['total'].sum()
    ganancia_neta = valor_mercancia_despachada - comisiones_punto_descontadas - costo_mercancia - egresos_hoy
    
    dinero_ventas = df_ventas_comerciales['total'].sum() if not df_ventas_comerciales.empty else 0.0
    dinero_abonos = df_abonos['total'].sum() if not df_abonos.empty else 0.0
    caja_final = dinero_ventas + dinero_abonos - egresos_hoy

    st.markdown("### 📈 1. Rendimiento y Rentabilidad del Día")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("📦 Valor Despachado", f"${valor_mercancia_despachada:.2f}")
    r2.metric("📉 Costo Insumos", f"${costo_mercancia:.2f}")
    r3.metric("📤 Egresos / Gastos", f"${egresos_hoy:.2f}")
    if ganancia_neta >= 0:
        r4.metric("💰 GANANCIA REAL", f"${ganancia_neta:.2f}")
    else:
        r4.metric("🚨 Pérdida", f"${ganancia_neta:.2f}", delta_color="inverse")
        
    st.markdown("---")
    
    st.markdown("### 💵 2. Arqueo y Desglose por Método de Pago")
    efectivo_usd_total = df_ventas_hoy['monto_efectivo_usd'].sum() if ('monto_efectivo_usd' in df_ventas_hoy.columns and not df_ventas_hoy.empty) else 0.0
    efectivo_bs_nominal = df_ventas_hoy['monto_efectivo_bs'].sum() if ('monto_efectivo_bs' in df_ventas_hoy.columns and not df_ventas_hoy.empty) else 0.0
    pago_movil_nominal = df_ventas_hoy['monto_pago_movil'].sum() if ('monto_pago_movil' in df_ventas_hoy.columns and not df_ventas_hoy.empty) else 0.0
    punto_neto_nominal = df_ventas_hoy['monto_punto'].sum() if ('monto_punto' in df_ventas_hoy.columns and not df_ventas_hoy.empty) else 0.0

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("💵 Efectivo USD", f"${efectivo_usd_total:.2f}")
    d2.metric("🇻🇪 Efectivo Bs.", f"{efectivo_bs_nominal:,.2f} Bs.")
    d3.metric("📱 Pago Móvil / Transf.", f"{pago_movil_nominal:,.2f} Bs.")
    d4.metric("💳 Punto Neto (-2%)", f"{punto_neto_nominal:,.2f} Bs.")
    
    st.markdown("---")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("📥 Total Ingresado Hoy", f"${dinero_ventas + dinero_abonos:.2f}")
    c2.metric("📤 Egresos del Día", f"${egresos_hoy:.2f}")
    c3.metric("⚖️ BALANCE ESPERADO EN CAJA", f"${caja_final:.2f}")
    
    st.markdown("---")
    col_izq, col_der = st.columns(2)
    
    with col_izq:
        st.markdown("#### 💳 Resumen de Canales")
        df_resumen_metodos = pd.DataFrame([
            {"Canal": "💵 Efectivo USD", "Monto ($)": efectivo_usd_total, "Monto (Bs.)": round(efectivo_usd_total * tasa_dolar, 2)},
            {"Canal": "🇻🇪 Efectivo Bs.", "Monto ($)": efectivo_bs_nominal / tasa_dolar if tasa_dolar > 0 else 0, "Monto (Bs.)": round(efectivo_bs_nominal, 2)},
            {"Canal": "📱 Pago Móvil", "Monto ($)": pago_movil_nominal / tasa_dolar if tasa_dolar > 0 else 0, "Monto (Bs.)": round(pago_movil_nominal, 2)},
            {"Canal": "💳 Punto Venta Net", "Monto ($)": punto_neto_nominal / tasa_dolar if tasa_dolar > 0 else 0, "Monto (Bs.)": round(punto_neto_nominal, 2)}
        ])
        st.dataframe(df_resumen_metodos, use_container_width=True, hide_index=True)
            
    with col_der:
        st.markdown("#### 🏆 Producto Estrella de Hoy")
        query_top = """SELECT p.nombre, SUM(vd.cantidad) as total_vendido 
                       FROM ventas_detalle vd 
                       JOIN productos p ON vd.producto_id = p.id 
                       JOIN ventas_maestro vm ON vd.venta_id = vm.id 
                       WHERE vm.fecha LIKE ? 
                       GROUP BY p.nombre ORDER BY total_vendido DESC LIMIT 1"""
        try:
            df_top = pd.read_sql_query(query_top, conn, params=(param_hoy,))
            if not df_top.empty:
                st.info(f"🥇 **{df_top.iloc[0]['nombre']}** — Despachados: {int(df_top.iloc[0]['total_vendido'])} U")
            else:
                st.info("Aún no hay ventas suficientes.")
        except:
            pass

    st.markdown("---")
    if st.button("🏁 EJECUTAR CIERRE DE CAJA DIARIO", type="primary"):
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO cierres_diarios 
            (fecha, ganancia_neta, efectivo_usd, efectivo_bs, punto_neto, pago_movil_transferencia, balance_total_usd) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (hoy, ganancia_neta, efectivo_usd_total, efectivo_bs_nominal, punto_neto_nominal, pago_movil_nominal, caja_final))
        conn.commit()
        
        with st.container(border=True):
            st.markdown(f"### 📋 CIERRE REGISTRADO - {hoy}")
            st.markdown(f"**Ganancia del Negocio:** `${ganancia_neta:.2f}`")
            st.markdown(f"**Balance Esperado:** `${caja_final:.2f}`")
            st.success("🔒 ¡Cierre guardado correctamente en el historial!")
            st.balloons()

elif modulo == "📜 Historial de Cierres":
    st.title("📜 Historial de Cierres")
    st.caption("Consulta los cierres diarios guardados y exporta la información en formato Excel.")
    
    query_cierres = """
        SELECT 
            fecha as 'Fecha', 
            ganancia_neta as 'Ganancia Real ($)', 
            efectivo_usd as 'Efectivo USD ($)', 
            efectivo_bs as 'Efectivo Bs (Bs.)', 
            punto_neto as 'Punto Neto (Bs.)', 
            pago_movil_transferencia as 'Pago Móvil (Bs.)', 
            balance_total_usd as 'Balance Total ($)' 
        FROM cierres_diarios ORDER BY id DESC
    """
    df_cierres = pd.read_sql_query(query_cierres, conn)
    
    if not df_cierres.empty:
        st.dataframe(df_cierres, use_container_width=True, hide_index=True)
        
        def convertir_a_excel(df):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Cierres Diarios')
            return output.getvalue()
            
        excel_data = convertir_a_excel(df_cierres)
        
        st.download_button(
            label="📊 Descargar Reporte en Excel",
            data=excel_data,
            file_name=f"Reporte_Cierres_PuntoYali_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
    else:
        st.info("No hay cierres diarios registrados todavía.")

if conn:
    conn.close()
