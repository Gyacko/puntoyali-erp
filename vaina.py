import os
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io

try:
    import libsql
except ImportError:
    libsql = None

# --- CONFIGURACIÓN DE INTERFAZ Y ESTILOS MÓVIL/MINIMALISTAS ---
st.set_page_config(page_title="Punto Yali - ERP", layout="wide")

st.markdown("""
    <style>
    /* Ocultar elementos predeterminados de Streamlit para una vista limpia */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Espaciado general optimizado para pantallas táctiles */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
    }

    /* Tarjetas y contenedores con diseño minimalista moderno */
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.15);
        padding: 16px;
        background-color: rgba(255, 255, 255, 0.015);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }

    /* Botones más grandes y cómodos para presionar en el celular */
    .stButton button {
        border-radius: 8px;
        font-weight: 600;
        width: 100%;
        height: 3rem;
        transition: all 0.2s ease-in-out;
    }
    
    /* Métricas con diseño limpio */
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.03);
        padding: 12px;
        border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.1);
    }
    </style>
""", unsafe_allow_html=True)

# --- CONFIGURACIÓN DE BASE DE DATOS (HÍBRIDA: LOCAL O TURSO) ---
def conectar_db():
    usar_turso = False
    turso_url = None
    turso_token = None
    
    # 1. Intentar leer de st.secrets (Streamlit Cloud)
    try:
        if "TURSO_URL" in st.secrets and libsql is not None:
            turso_url = st.secrets["TURSO_URL"]
            turso_token = st.secrets.get("TURSO_TOKEN", "")
            usar_turso = True
    except Exception:
        pass
        
    # 2. Intentar leer de variables de entorno (Railway, Render, etc.)
    if not usar_turso and libsql is not None:
        if os.getenv("TURSO_URL"):
            turso_url = os.getenv("TURSO_URL")
            turso_token = os.getenv("TURSO_TOKEN", "")
            usar_turso = True

    if usar_turso and turso_url:
        conn = libsql.connect(
            database=turso_url,
            auth_token=turso_token
        )
    else:
        conn = sqlite3.connect('sistema_negocio.db', timeout=10, check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
        except Exception:
            pass
    return conn

def parse_float(val, default=0.0):
    """Conversor inteligente para aceptar puntos y comas en los inputs de texto"""
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
    cursor.execute('''CREATE TABLE IF NOT EXISTS cierres_diarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        fecha TEXT, 
        ganancia_neta REAL,
        efectivo_usd REAL,
        efectivo_bs REAL,
        punto_neto REAL,
        pago_movil_transferencia REAL,
        balance_total_usd REAL
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        nombre TEXT UNIQUE, 
        categoria TEXT, 
        precio_venta REAL, 
        costo_insumo REAL, 
        porcentaje_ganancia REAL DEFAULT 0,
        aplica_iva INTEGER DEFAULT 0,
        stock REAL
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS ventas_maestro (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        fecha TEXT, 
        subtotal REAL, 
        impuesto REAL, 
        total REAL, 
        metodo_pago TEXT, 
        cliente TEXT,
        monto_efectivo_usd REAL DEFAULT 0,
        monto_efectivo_bs REAL DEFAULT 0,
        monto_pago_movil REAL DEFAULT 0,
        monto_punto REAL DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS ventas_detalle (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        venta_id INTEGER, 
        producto_id INTEGER, 
        cantidad INTEGER, 
        precio_unitario REAL, 
        FOREIGN KEY(venta_id) REFERENCES ventas_maestro(id), 
        FOREIGN KEY(producto_id) REFERENCES productos(id)
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS egresos_maestro (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        fecha TEXT, 
        proveedor TEXT, 
        tipo_gasto TEXT, 
        subtotal REAL, 
        porcentaje_impuesto REAL, 
        monto_impuesto REAL, 
        total REAL,
        origen_fondo TEXT DEFAULT 'Banco Bs.',
        monto_efectivo_usd REAL DEFAULT 0,
        monto_efectivo_bs REAL DEFAULT 0,
        monto_bancos_bs REAL DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS egresos_detalle (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        egreso_id INTEGER, 
        producto_id INTEGER, 
        cantidad INTEGER, 
        costo_unitario REAL, 
        FOREIGN KEY(egreso_id) REFERENCES egresos_maestro(id), 
        FOREIGN KEY(producto_id) REFERENCES productos(id)
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS deudas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        cliente TEXT, 
        monto_total REAL, 
        saldo_pendiente REAL, 
        fecha_origen TEXT, 
        ultima_actualizacion TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS prestamos_personales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        persona TEXT,
        monto REAL,
        concepto TEXT,
        estado TEXT DEFAULT 'Pendiente'
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial_inventario (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        producto_id INTEGER, 
        producto_nombre TEXT, 
        fecha TEXT, 
        stock_anterior REAL, 
        stock_nuevo REAL, 
        motivo TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS movimientos_capital (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        tipo TEXT,
        efectivo_usd REAL DEFAULT 0,
        efectivo_bs REAL DEFAULT 0,
        bancos_bs REAL DEFAULT 0,
        concepto TEXT
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS categorias (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS notas_generales (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, nota TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT)''')
    
    cursor.execute("SELECT COUNT(*) FROM configuracion WHERE clave = 'tasa_dolar'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO configuracion (clave, valor) VALUES ('tasa_dolar', '880.0')")

    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        cats_iniciales = ["Papelería", "Cigarrillos", "Heladería", "Impresiones y Diseño", "Otros"]
        for c in cats_iniciales:
            cursor.execute("INSERT OR IGNORE INTO categorias (nombre) VALUES (?)", (c,))
            
    conn.commit()
    conn.close()

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
    conn.close()

@st.cache_data(ttl=120)
def obtener_tasa_actual():
    with conectar_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracion WHERE clave = 'tasa_dolar'")
        resultado = cursor.fetchone()
        return float(resultado[0]) if resultado else 880.0

def guardar_tasa_actual(nueva_tasa):
    with conectar_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('tasa_dolar', ?)", (str(nueva_tasa),))
        conn.commit()
    obtener_tasa_actual.clear()

# --- OPTIMIZACIÓN: INICIALIZACIÓN ÚNICA POR SESIÓN ---
if 'db_inicializada' not in st.session_state:
    inicializar_db()
    migracion_segura_db()
    st.session_state.db_inicializada = True

if 'carrito' not in st.session_state:
    st.session_state.carrito = []

# =========================================================================
# --- ENCABEZADO SUPERIOR MÓVIL (VISIBLE DIRECTAMENTE EN LA PARTE ALTA) ---
# =========================================================================
st.markdown("### 🏛️ Punto Yali - ERP")

col_tasa_m, col_mod_m = st.columns([1, 2])
with col_tasa_m:
    tasa_guardada = obtener_tasa_actual()
    tasa_dolar = st.number_input("Tasa ($ / Bs.)", min_value=1.0, value=tasa_guardada, step=0.10, format="%.2f")
    if tasa_dolar != tasa_guardada:
        guardar_tasa_actual(tasa_dolar)

with col_mod_m:
    modulos_lista = [
        "🛒 Registrar Venta (Punto de Venta)", 
        "📦 Inventario y Productos", 
        "📊 Dashboard / Cierre Caja", 
        "📉 Egresos e Impuestos",
        "💰 Finanzas y Capital",
        "👥 Control de Deudores (Fiados)",
        "🛠️ Mantenimiento de Sistema",
        "📜 Historial de Cierres"  
    ]
    modulo = st.selectbox("📌 ¿Qué deseas hacer?", modulos_lista, label_visibility="visible")

st.markdown("---")

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
# MÓDULO: INVENTARIO Y PRODUCTOS
# ==========================================
elif modulo == "📦 Inventario y Productos":
    st.title("📦 Centro de Control de Inventario")
    st.caption("Gestión ágil de existencias, precios y creación de artículos.")
    
    tab_inv, tab_nuevo, tab_cat, tab_pizarra, tab_hist = st.tabs([
        "📋 Existencias", "➕ Nuevo", "📁 Categorías", "📝 Pizarra", "📜 Auditoría"
    ])
    
    lista_cats_db = pd.read_sql_query("SELECT nombre FROM categorias", conn)['nombre'].tolist()
    
    with tab_inv:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            cat_filtro = st.selectbox("🔍 Categoría:", ["Todas las Categorías"] + lista_cats_db)
        with col_f2:
            busq_texto = st.text_input("🔎 Buscar:", placeholder="Nombre del artículo...")
        
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
            
            if paginas_totales > 1:
                pagina_actual = st.selectbox("📄 Página:", range(1, paginas_totales + 1), format_func=lambda x: f"Página {x} de {paginas_totales}")
            else:
                pagina_actual = 1
            
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
                    info_extra_str = f" | 🚬 Suelto: **${p_unit_suelto:.3f}**"
                
                with st.expander(f"📦 **{p_nombre}** | Stock: **{p_stock:.1f} U** ({estado_txt}) | **${p_precio:.2f}**"):
                    with st.form(f"form_edit_{p_id}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            e_nombre = st.text_input("Nombre del Artículo", value=p_nombre, key=f"nom_{p_id}")
                            e_cat = st.selectbox("Categoría", lista_cats_db, index=lista_cats_db.index(p_cat) if p_cat in lista_cats_db else 0, key=f"cat_{p_id}")
                            
                            e_costo_str = st.text_input("Costo Base ($)", value=str(p_costo), key=f"costo_{p_id}")
                            e_ganancia_str = st.text_input("Ganancia (%)", value=str(p_ganancia), key=f"gan_{p_id}")
                            e_iva = st.checkbox("🏛️ ¿Aplica IVA (16%)?", value=p_iva, key=f"iva_{p_id}")
                            
                            e_costo = parse_float(e_costo_str, p_costo)
                            e_ganancia = parse_float(e_ganancia_str, p_ganancia)
                            
                            m_dec = e_ganancia / 100
                            div = 1.0 - m_dec if m_dec < 1.0 else 0.01
                            p_sin_i = e_costo / div if div > 0 else e_costo
                            e_pv = p_sin_i * 1.16 if e_iva else p_sin_i
                            st.info(f"💵 **Venta Calc:** ${e_pv:.2f}")
                            
                        with c2:
                            e_stock_str = st.text_input("Stock Actual", value=str(p_stock), key=f"stk_{p_id}")
                            e_motivo = st.text_input("Motivo de ajuste", placeholder="Ej: Conteo físico...", key=f"mot_{p_id}")
                            e_es_cig = st.checkbox("📦 Caja / Detallado", value=p_es_cig, key=f"cig_{p_id}")
                            e_u_caja_str = st.text_input("Unidades por caja", value=str(p_u_caja), key=f"ucaj_{p_id}")
                            
                            e_stock = parse_float(e_stock_str, p_stock)
                            e_u_caja = parse_float(e_u_caja_str, p_u_caja)
                            e_obs = st.text_area("Observaciones", value=p_obs, key=f"obs_{p_id}")
                            
                        guardar_cambio = st.form_submit_button("💾 Guardar Cambios de este Artículo", type="primary")
                        
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
                            st.success(f"✔️ Actualizado con éxito.")
                            st.rerun()

                    confirmar_del = st.checkbox(f"⚠️ Activar opción para eliminar '{p_nombre}'", key=f"chk_del_{p_id}")
                    if confirmar_del:
                        if st.button(f"🗑️ ELIMINAR ESTE PRODUCTO", key=f"btn_del_{p_id}", type="primary"):
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM productos WHERE id = ?", (p_id,))
                            cursor.execute("DELETE FROM historial_inventario WHERE producto_id = ?", (p_id,))
                            conn.commit()
                            st.error(f"💥 Producto eliminado.")
                            st.rerun()
        else:
            st.info("No se encontraron productos.")

    with tab_nuevo:
        st.subheader("➕ Registrar Nuevo Producto")
        with st.form("form_nuevo_prod_seguro"):
            col1, col2 = st.columns(2)
            with col1:
                nombre_n = st.text_input("Nombre del Artículo")
                categoria_n = st.selectbox("Categoría", lista_cats_db if lista_cats_db else ["Otros"], key="cat_nuevo")
                
                costo_str_n = st.text_input("Costo Base ($)", value="0.00", key="costo_nuevo")
                ganancia_str_n = st.text_input("Ganancia (%)", value="40.00", key="gan_nuevo")
                iva_n = st.checkbox("🏛️ ¿Aplica IVA (16%)?", key="iva_nuevo")
                
                costo_n = parse_float(costo_str_n)
                ganancia_n = parse_float(ganancia_str_n, 40.0)
                
                m_dec_n = ganancia_n / 100
                div_n = 1.0 - m_dec_n if m_dec_n < 1.0 else 0.01
                p_sin_iva_n = costo_n / div_n if div_n > 0 else costo_n
                precio_v_n = p_sin_iva_n * 1.16 if iva_n else p_sin_iva_n
                
                st.info(f"💵 **Precio Venta:** ${precio_v_n:.2f}")

            with col2:
                stock_str_n = st.text_input("Stock Inicial", value="0", key="stock_nuevo")
                obs_n = st.text_area("Observaciones", placeholder="Detalles...", key="obs_nuevo")
                stock_n = parse_float(stock_str_n)
                
                st.markdown("---")
                es_cig_n = st.checkbox("📦 ¿Se vende por caja y suelto?", key="cig_nuevo")
                u_caja_str_n = st.text_input("Unidades en caja", value="20", key="ucaj_nuevo")
                u_caja_n = parse_float(u_caja_str_n, 20.0)
            
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
                        st.error("❌ Ya existe un producto con ese nombre.")
                else:
                    st.warning("⚠️ Debes asignar un nombre.")

    with tab_cat:
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
        st.markdown("**Categorías Activas:**")
        for cat in lista_cats_db:
            st.markdown(f"- 🏷️ {cat}")

    with tab_pizarra:
        nota_texto = st.text_area("Nueva nota:", placeholder="Recordatorio...")
        if st.button("📌 Publicar Nota"):
            if nota_texto:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO notas_generales (fecha, nota) VALUES (?, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), nota_texto))
                conn.commit()
                st.rerun()
        
        df_notas = pd.read_sql_query("SELECT id, fecha, nota FROM notas_generales ORDER BY id DESC", conn)
        if not df_notas.empty:
            for _, row in df_notas.iterrows():
                with st.container(border=True):
                    st.caption(f"🗓️ {row['fecha']}")
                    st.write(row['nota'])
                    if st.button("🗑️ Borrar", key=f"del_nota_{row['id']}"):
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM notas_generales WHERE id=?", (row['id'],))
                        conn.commit()
                        st.rerun()

    with tab_hist:
        df_hist = pd.read_sql_query("SELECT fecha as 'Fecha', producto_nombre as 'Producto', stock_anterior as 'Antes', stock_nuevo as 'Nuevo', motivo as 'Motivo' FROM historial_inventario ORDER BY id DESC", conn)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

# ==========================================
# MÓDULO: PUNTO DE VENTA (POS)
# ==========================================
elif modulo == "🛒 Registrar Venta (Punto de Venta)":
    st.title("🛒 Punto de Venta (POS)")
    st.caption("Facturación rápida y control automático de caja.")
    
    df_prod = pd.read_sql_query("SELECT * FROM productos", conn)
    
    if df_prod.empty:
        st.warning("El inventario está vacío.")
    else:
        with st.container(border=True):
            prod_nombre = st.selectbox("Seleccionar Producto", df_prod['nombre'].tolist())
            info_p = df_prod[df_prod['nombre'] == prod_nombre].iloc[0]
            stock_actual = float(info_p['stock'])
            es_cigarrillo = int(info_p['es_cigarrillo'] if info_p['es_cigarrillo'] else 0)
            u_caja = float(info_p['unidades_por_caja'] if info_p['unidades_por_caja'] else 1.0)
            
            if es_cigarrillo == 1:
                opcion_empaque = st.radio("Empaque", ["Unidad/Suelto", "Caja Cerrada"], horizontal=True)
                if opcion_empaque == "Unidad/Suelto" and u_caja > 0:
                    precio_unit_calc = float(info_p['precio_venta']) / u_caja
                    st.caption(f"Stock: {stock_actual:.1f} U | C/U: ${precio_unit_calc:.3f}")
                else:
                    st.caption(f"Stock: {stock_actual:.1f} U")
            else:
                opcion_empaque = "Normal"
                st.caption(f"Stock: {stock_actual:.1f} U")
            
            precio_defecto_usd = float(info_p['precio_venta'])
            if st.checkbox("Precio Manual"):
                precio_manual_bs = st.number_input("Precio en Bs.", min_value=0.0, value=round(precio_defecto_usd * tasa_dolar, 2))
                precio_final = precio_manual_bs / tasa_dolar if tasa_dolar > 0 else 0.0
            else:
                precio_final = precio_defecto_usd
                st.text(f"Ref: ${precio_final:.2f}")
                
            cant_vender = st.number_input("Cantidad", min_value=1, value=1, step=1)
            
            if st.button("➕ Agregar al Carrito", type="primary"):
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
                st.success("¡Agregado!")
                st.rerun()

        if st.session_state.carrito:
            st.markdown("---")
            st.markdown("### 🛍️ Carrito Actual")
            
            carrito_actualizado = []
            for i, item in enumerate(st.session_state.carrito):
                with st.container(border=True):
                    st.markdown(f"**{item['nombre']}**")
                    p_u_usd = item['precio_u']
                    p_u_bs = p_u_usd * tasa_dolar
                    st.caption(f"Unitario: ${p_u_usd:.3f} ({p_u_bs:.2f} Bs.)")
                    
                    nueva_cant = st.number_input("Cantidad", min_value=1, value=int(item['cantidad_pantalla']), key=f"cant_item_{i}")
                    sub_usd = nueva_cant * item['precio_u']
                    sub_bs = sub_usd * tasa_dolar
                    st.write(f"**Subtotal:** ${sub_usd:.2f} *({sub_bs:.2f} Bs.)*")
                    
                    eliminar = st.button("🗑️ Quitar artículo", key=f"del_item_{i}")
                    
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
                col_bs.metric("TOTAL BS", f"{total_bs:.2f} Bs.")
                
                with st.container(border=True):
                    st.subheader("💳 Cierre Financiero")
                    pago_mixto = st.checkbox("🔀 Pago fraccionado / mixto")
                    vuelto_usd = 0.0
                    vuelto_bs = 0.0
                    
                    if not pago_mixto:
                        metodo_pago = st.selectbox("Método de Pago", ["Efectivo (Divisa/USD)", "Efectivo (Bolívares)", "Pago Móvil / Transferencia", "Punto de Venta (Tarjeta)", "Fiado (Crédito)", "Consumo Interno"])
                        
                        if metodo_pago == "Fiado (Crédito)":
                            df_deudores_activos = pd.read_sql_query("SELECT DISTINCT cliente FROM deudas WHERE saldo_pendiente >= 0.01", conn)
                            lista_deudores_activos = df_deudores_activos['cliente'].tolist() if not df_deudores_activos.empty else []
                            
                            opciones_deudor = ["-- Seleccionar deudor --", "➕ Registrar Nuevo Deudor"] + lista_deudores_activos
                            sel_deudor_pos = st.selectbox("Seleccionar Deudor", opciones_deudor)
                            
                            if sel_deudor_pos == "➕ Registrar Nuevo Deudor":
                                cliente_name = st.text_input("Nombre del nuevo deudor:")
                            elif sel_deudor_pos == "-- Seleccionar deudor --":
                                cliente_name = ""
                            else:
                                cliente_name = sel_deudor_pos
                        elif metodo_pago == "Punto de Venta (Tarjeta)":
                            cliente_name = st.text_input("Cliente / Referencia")
                        else:
                            cliente_name = ""
                        
                        m_ef_usd = total_usd if metodo_pago == "Efectivo (Divisa/USD)" else 0.0
                        m_ef_bs = total_bs if metodo_pago == "Efectivo (Bolívares)" else 0.0
                        m_pm = total_bs if metodo_pago == "Pago Móvil / Transferencia" else 0.0
                        m_ptv = total_bs * 0.98 if metodo_pago == "Punto de Venta (Tarjeta)" else 0.0
                        
                        if metodo_pago == "Efectivo (Divisa/USD)":
                            monto_recibido_usd = st.number_input("💵 Recibido en Efectivo USD ($)", min_value=float(round(total_usd, 2)), value=float(round(total_usd, 2)))
                            vuelto_usd = round(monto_recibido_usd - total_usd, 2)
                            vuelto_bs = round(vuelto_usd * tasa_dolar, 2)
                            st.info(f"💵 **VUELTO:** ${vuelto_usd:.2f} *({vuelto_bs:.2f} Bs.)*")
                            
                        elif metodo_pago == "Efectivo (Bolívares)":
                            monto_recibido_bs = st.number_input("💵 Recibido en Efectivo Bs.", min_value=float(round(total_bs, 2)), value=float(round(total_bs, 2)))
                            vuelto_bs = round(monto_recibido_bs - total_bs, 2)
                            vuelto_usd = round(vuelto_bs / tasa_dolar, 2) if tasa_dolar > 0 else 0.0
                            st.info(f"💵 **VUELTO:** {vuelto_bs:.2f} Bs. *(${vuelto_usd:.2f})*")

                        monto_ingreso_caja = total_usd if metodo_pago != "Punto de Venta (Tarjeta)" else total_usd * 0.98
                        if metodo_pago in ["Consumo Interno", "Fiado (Crédito)"]:
                            monto_ingreso_caja = 0.0
                            m_ef_usd = m_ef_bs = m_pm = m_ptv = 0.0
                            
                        metodo_final_str = metodo_pago
                        bloquear_registro = False
                        
                        if metodo_pago == "Fiado (Crédito)" and not cliente_name:
                            st.warning("⚠️ Debes seleccionar o registrar un deudor.")
                            bloquear_registro = True
                        
                    else:
                        p_ef_usd = st.number_input("Efectivo USD ($)", min_value=0.0, value=0.0, key="mix_ef_usd")
                        p_ef_bs = st.number_input("Efectivo Bs.", min_value=0.0, value=0.0, key="mix_ef_bs")
                        p_pm = st.number_input("Pago Móvil", min_value=0.0, value=0.0, key="mix_pm")
                        p_ptv_bruto = st.number_input("Punto Venta", min_value=0.0, value=0.0, key="mix_ptv")
                        
                        p_ptv_neto = p_ptv_bruto * 0.98
                        suma_parcial_usd = p_ef_usd + (p_ef_bs / tasa_dolar if tasa_dolar > 0 else 0) + (p_pm / tasa_dolar if tasa_dolar > 0 else 0) + (p_ptv_neto / tasa_dolar if tasa_dolar > 0 else 0)
                        diferencia = round(suma_parcial_usd - total_usd, 2)
                        
                        if diferencia < -0.01:
                            st.warning(f"⚠️ Faltan por distribuir **${abs(diferencia):.2f}**")
                            bloquear_registro = True
                        elif diferencia > 0.01:
                            st.success(f"✅ VUELTO: ${diferencia:.2f}")
                            bloquear_registro = False
                        else:
                            st.success("✅ ¡Montos exactos!")
                            bloquear_registro = False
                            
                        cliente_name = ""
                        m_ef_usd = p_ef_usd
                        m_ef_bs = p_ef_bs
                        m_pm = p_pm
                        m_ptv = p_ptv_neto
                        monto_ingreso_caja = total_usd if total_usd > 0 else 0.0
                        metodo_final_str = "Pago Mixto"

                    if st.button("🗑️ Cancelar Venta"):
                        st.session_state.carrito = []
                        st.rerun()
                        
                    if st.button("✅ Registrar Venta", type="primary", disabled=bloquear_registro):
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
                        st.success("🎉 ¡Venta procesada con éxito!")
                        st.rerun()

# ==========================================
# MÓDULO: EGRESOS E IMPUESTOS
# ==========================================
elif modulo == "📉 Egresos e Impuestos":
    st.title("📉 Libro de Egresos e Impuestos")
    st.caption("Control de gastos operativos y tributos.")
    
    t1, t2 = st.tabs(["💸 Registrar Egreso", "🏛️ Impuestos"])
    
    with t1:
        with st.form("form_egresos"):
            tipo = st.selectbox("Tipo de Gasto", ["Compra de Mercancía/Insumos", "Pago de Salarios", "Servicios Públicos", "Seguro de Punto de Venta", "Impuestos Alcaldía"])
            desc = st.text_input("Detalle / Proveedor")
            moneda_egreso = st.selectbox("Moneda", ["Dólares ($)", "Bolívares (Bs.)"])
            monto_eg = st.number_input("Monto", min_value=0.0, format="%.2f")
            origen_egreso = st.selectbox("Origen del dinero", ["Efectivo USD", "Efectivo Bs.", "Banco / Cuenta Bs."])
            
            if st.form_submit_button("Registrar Egreso", type="primary"):
                if monto_eg <= 0:
                    st.error("❌ Monto inválido.")
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
                    st.success("✔️ Egreso guardado con éxito.")
                    st.rerun()
                
    with t2:
        st.subheader("Cálculo de Alcaldía")
        dias_historia = st.number_input("Días hacia atrás", min_value=1, value=7)
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
        porcentaje_alcaldia = st.slider("Impuesto Municipal (%)", min_value=1.0, max_value=5.0, value=2.0, step=0.5)
        
        if ganancia_neta_acumulada > 0:
            impuesto_a_pagar = ganancia_neta_acumulada * (porcentaje_alcaldia / 100)
            st.success(f"**Ganancia Neta:** ${ganancia_neta_acumulada:.2f} | **A Pagar:** ${impuesto_a_pagar:.2f}")
        else:
            impuesto_a_pagar = 0.0
            st.warning("Sin ganancias gravables.")
            
        if st.button("🏛️ Pagar Alcaldía", disabled=(impuesto_a_pagar<=0), type="primary"):
            cursor = conn.cursor()
            cursor.execute("""INSERT INTO egresos_maestro 
                (fecha, proveedor, tipo_gasto, subtotal, porcentaje_impuesto, monto_impuesto, total, origen_fondo, monto_efectivo_usd, monto_efectivo_bs, monto_bancos_bs) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Alcaldía", "Impuestos Alcaldía", impuesto_a_pagar, 0.0, 0.0, impuesto_a_pagar, "Banco Bs.", 0.0, 0.0, impuesto_a_pagar * tasa_dolar))
            conn.commit()
            st.rerun()

# ==========================================
# MÓDULO: FINANZAS Y CAPITAL
# ==========================================
elif modulo == "💰 Finanzas y Capital":
    st.title("💰 Módulo de Finanzas y Capital")
    st.caption("Tesorería unificada.")
    
    PIN_SECRETO = "1234"
    password_input = st.text_input("🔒 Contraseña de seguridad:", type="password")
    
    if password_input != PIN_SECRETO:
        if password_input != "":
            st.error("❌ Contraseña incorrecta.")
        st.stop()
    
    st.success("🔓 Acceso autorizado.")
    st.markdown("---")
    
    df_movs = pd.read_sql_query("SELECT tipo, efectivo_usd, efectivo_bs, bancos_bs FROM movimientos_capital", conn)
    ef_usd_mov = ef_bs_mov = bancos_bs_mov = 0.0
    
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
                
    st.markdown("### 🏛️ Saldos Reales")
    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("💵 Ef. USD", f"${acum_ef_usd:,.2f}")
    col_s2.metric("💵 Ef. Bs", f"{acum_ef_bs:,.2f} Bs.")
    col_s3.metric("🏦 Bancos", f"{acum_bancos_bs:,.2f} Bs.")
    
    st.markdown("---")
    with st.form("form_mov_capital_separado"):
        tipo_mov = st.selectbox("Operación", ["Inyección de Capital", "Retiro de Capital"])
        m_ef_usd = st.number_input("Efectivo USD ($)", min_value=0.0, value=0.0)
        m_ef_bs = st.number_input("Efectivo Bs.", min_value=0.0, value=0.0)
        m_bancos_bs = st.number_input("Banco (Bs.)", min_value=0.0, value=0.0)
        concepto_mov = st.text_input("Concepto", placeholder="Descripción...")
        
        if st.form_submit_button("💾 Guardar Movimiento", type="primary"):
            if m_ef_usd <= 0 and m_ef_bs <= 0 and m_bancos_bs <= 0:
                st.error("❌ Ingresa un monto válido.")
            else:
                cursor = conn.cursor()
                cursor.execute("""INSERT INTO movimientos_capital 
                    (fecha, tipo, efectivo_usd, efectivo_bs, bancos_bs, concepto) 
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tipo_mov, m_ef_usd, m_ef_bs, m_bancos_bs, concepto_mov if concepto_mov else tipo_mov))
                conn.commit()
                st.success("✔️ Movimiento registrado.")
                st.rerun()

# ==========================================
# MÓDULO: DEUDORES (FIADOS)
# ==========================================
elif modulo == "👥 Control de Deudores (Fiados)":
    st.title("👥 Cuentas por Cobrar (Fiados)")
    st.caption("Desglose individual por deudor y abonos.")
    
    df_deudas = pd.read_sql_query("SELECT id, cliente, saldo_pendiente FROM deudas WHERE saldo_pendiente >= 0.01", conn)
    
    if not df_deudas.empty:
        for _, row in df_deudas.iterrows():
            cliente_actual = row['cliente']
            saldo_usd = float(row['saldo_pendiente'])
            saldo_bs = saldo_usd * tasa_dolar
            
            with st.expander(f"👤 **{cliente_actual}** — Deuda: **${saldo_usd:.2f}** *({saldo_bs:,.2f} Bs.)*"):
                query_articulos = """
                    SELECT p.nombre, vd.cantidad, vd.precio_unitario, vm.fecha
                    FROM ventas_detalle vd
                    JOIN productos p ON vd.producto_id = p.id
                    JOIN ventas_maestro vm ON vd.venta_id = vm.id
                    WHERE vm.cliente = ? AND vm.metodo_pago = 'Fiado (Crédito)'
                """
                df_articulos = pd.read_sql_query(query_articulos, conn, params=(cliente_actual,))
                
                if not df_articulos.empty:
                    items_formateados = []
                    for _, art in df_articulos.iterrows():
                        p_u_usd = float(art['precio_unitario'])
                        cant = art['cantidad']
                        sub_usd = cant * p_u_usd
                        items_formateados.append({
                            "Fecha": art['fecha'],
                            "Artículo": art['nombre'],
                            "Cant.": cant,
                            "Subtotal ($)": f"${sub_usd:.2f}"
                        })
                    st.dataframe(pd.DataFrame(items_formateados), use_container_width=True, hide_index=True)

                monto_abono = st.number_input("Monto a abonar ($)", min_value=0.01, max_value=saldo_usd, value=saldo_usd, key=f"abono_{row['id']}")
                metodo_pago_abono = st.selectbox("Método de Abono", ["Efectivo (Divisa/USD)", "Efectivo (Bolívares)", "Pago Móvil / Transferencia", "Punto de Venta (Tarjeta)"], key=f"metodo_abono_{row['id']}")
                
                if st.button("✅ Procesar Abono", key=f"btn_abono_{row['id']}", type="primary"):
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
                        
                    cursor.execute("""INSERT INTO ventas_maestro 
                        (fecha, subtotal, impuesto, total, metodo_pago, cliente, monto_efectivo_usd, monto_efectivo_bs, monto_pago_movil, monto_punto) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (ahora_exacto, monto_abono, 0.0, monto_ingreso_caja, f"Abono - {metodo_pago_abono}", f"Abono Deuda - {cliente_actual}", m_ef_usd, m_ef_bs, m_pm, m_ptv))
                    
                    conn.commit()
                    st.success("✅ Abono procesado con éxito.")
                    st.rerun()
    else:
        st.success("🎉 ¡Todos los clientes están al día!")

# ==========================================
# MÓDULO: DASHBOARD Y CIERRE
# ==========================================
elif modulo == "📊 Dashboard / Cierre Caja":
    st.title("📊 Panel de Control y Cierre de Caja")
    st.caption("Métricas financieras y arqueo diario.")
    
    fecha_seleccionada = st.date_input("📅 Día:", value=datetime.now())
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

    st.markdown("### 📈 Rendimiento del Día")
    st.metric("📦 Valor Despachado", f"${valor_mercancia_despachada:.2f}")
    st.metric("📤 Egresos", f"${egresos_hoy:.2f}")
    st.metric("💰 GANANCIA REAL", f"${ganancia_neta:.2f}")
        
    st.markdown("---")
    st.markdown("### 💵 Arqueo por Método")
    efectivo_usd_total = df_ventas_hoy['monto_efectivo_usd'].sum() if ('monto_efectivo_usd' in df_ventas_hoy.columns and not df_ventas_hoy.empty) else 0.0
    efectivo_bs_nominal = df_ventas_hoy['monto_efectivo_bs'].sum() if ('monto_efectivo_bs' in df_ventas_hoy.columns and not df_ventas_hoy.empty) else 0.0
    pago_movil_nominal = df_ventas_hoy['monto_pago_movil'].sum() if ('monto_pago_movil' in df_ventas_hoy.columns and not df_ventas_hoy.empty) else 0.0
    punto_neto_nominal = df_ventas_hoy['monto_punto'].sum() if ('monto_punto' in df_ventas_hoy.columns and not df_ventas_hoy.empty) else 0.0

    st.write(f"- 💵 Ef. USD: **${efectivo_usd_total:.2f}**")
    st.write(f"- 🇻🇪 Ef. Bs: **{efectivo_bs_nominal:,.2f} Bs.**")
    st.write(f"- 📱 Pago Móvil: **{pago_movil_nominal:,.2f} Bs.**")
    st.write(f"- 💳 Punto Neto: **{punto_neto_nominal:,.2f} Bs.**")
    
    st.markdown("---")
    st.metric("⚖️ BALANCE ESPERADO EN CAJA", f"${caja_final:.2f}")

    if st.button("🏁 EJECUTAR CIERRE DE CAJA DIARIO", type="primary"):
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO cierres_diarios 
            (fecha, ganancia_neta, efectivo_usd, efectivo_bs, punto_neto, pago_movil_transferencia, balance_total_usd) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (hoy, ganancia_neta, efectivo_usd_total, efectivo_bs_nominal, punto_neto_nominal, pago_movil_nominal, caja_final))
        conn.commit()
        st.success("🔒 ¡Cierre guardado con éxito!")
        st.balloons()

# ==========================================
# MÓDULO: HISTORIAL DE CIERRES
# ==========================================
elif modulo == "📜 Historial de Cierres":
    st.title("📜 Historial de Cierres")
    
    df_cierres = pd.read_sql_query("SELECT fecha as 'Fecha', ganancia_neta as 'Ganancia ($)', balance_total_usd as 'Balance ($)' FROM cierres_diarios ORDER BY id DESC", conn)
    
    if not df_cierres.empty:
        st.dataframe(df_cierres, use_container_width=True, hide_index=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_cierres.to_excel(writer, index=False, sheet_name='Cierres')
            
        st.download_button(
            label="📊 Descargar Excel",
            data=output.getvalue(),
            file_name=f"Cierres_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
    else:
        st.info("No hay cierres registrados.")

if conn:
    conn.close()
