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
    
    try:
        if "TURSO_URL" in st.secrets and libsql is not None:
            turso_url = st.secrets["TURSO_URL"]
            turso_token = st.secrets.get("TURSO_TOKEN", "")
            usar_turso = True
    except Exception:
        pass
        
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
        unidades_stock REAL DEFAULT 1,
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
        ultima_actualizacion TEXT,
        detalles TEXT DEFAULT ''
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
        ("ventas_detalle", "unidades_stock", "REAL DEFAULT 1"),
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

if 'db_inicializada' not in st.session_state:
    inicializar_db()
    migracion_segura_db()
    st.session_state.db_inicializada = True

if 'carrito' not in st.session_state:
    st.session_state.carrito = []

# --- ENCABEZADO SUPERIOR MÓVIL ---
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
    tab_borrado, tab_limpieza = st.tabs(["🎯 Borrado Quirúrgico", "🧹 Reseteo Total"])
    
    with tab_borrado:
        st.subheader("Eliminar Registros Específicos")
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
                    st.success(f"Venta/Abono {id_venta_del} eliminado.")
                    st.rerun()
            else:
                st.info("No hay ventas.")
                
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
                    st.success(f"Deuda {id_deuda_del} eliminada.")
                    st.rerun()
            else:
                st.info("No hay deudas.")

    with tab_limpieza:
        st.warning("⚠️ Borra todos los movimientos financieros, ventas, egresos y deudas. El inventario se mantiene.")
        confirmar_limpieza = st.checkbox("Entiendo y deseo borrar TODOS los movimientos financieros permanentemente.")
        if st.button("🚨 BORRAR MOVIMIENTOS FINANCIEROS", disabled=not confirmar_limpieza, type="primary"):
            cursor = conn.cursor()
            for tabla in ['ventas_maestro', 'ventas_detalle', 'egresos_maestro', 'egresos_detalle', 'deudas', 'historial_inventario', 'notas_generales', 'cierres_diarios', 'movimientos_capital', 'prestamos_personales']:
                try:
                    cursor.execute(f"DELETE FROM {tabla}")
                except Exception:
                    pass
            conn.commit()
            st.success("✅ Sistema limpiado.")
            st.balloons()

# ==========================================
# MÓDULO: INVENTARIO Y PRODUCTOS
# ==========================================
elif modulo == "📦 Inventario y Productos":
    st.title("📦 Centro de Control de Inventario")
    tab_inv, tab_nuevo, tab_cat, tab_pizarra, tab_hist = st.tabs(["📋 Existencias", "➕ Nuevo", "📁 Categorías", "📝 Pizarra", "📜 Auditoría"])
    lista_cats_db = pd.read_sql_query("SELECT nombre FROM categorias", conn)['nombre'].tolist()
    
    with tab_inv:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            cat_filtro = st.selectbox("🔍 Categoría:", ["Todas las Categorías"] + lista_cats_db)
        with col_f2:
            busq_texto = st.text_input("🔎 Buscar:", placeholder="Nombre...")
        
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
            pagina_actual = st.selectbox("📄 Página:", range(1, paginas_totales + 1), format_func=lambda x: f"Página {x} de {paginas_totales}") if paginas_totales > 1 else 1
            
            inicio = (pagina_actual - 1) * ITEMS_POR_PAGINA
            df_pagina = df_prod.iloc[inicio:inicio + ITEMS_POR_PAGINA]
            
            for _, prod in df_pagina.iterrows():
                p_id, p_nombre, p_cat, p_costo = int(prod['id']), prod['nombre'], prod['categoria'], float(prod['costo_insumo'])
                p_ganancia = float(prod.get('porcentaje_ganancia', 40.0))
                p_iva = int(prod.get('aplica_iva', 0)) == 1
                p_stock, p_precio = float(prod['stock']), float(prod['precio_venta'])
                p_obs = str(prod['observaciones'] or '')
                p_es_cig = int(prod.get('es_cigarrillo', 0)) == 1
                p_u_caja = float(prod.get('unidades_por_caja', 1.0))
                estado_txt = "🔴 Crítico" if p_stock <= 3 else ("🟡 Bajo" if p_stock <= 10 else "🟢 Normal")
                
                with st.expander(f"📦 **{p_nombre}** | Stock: **{p_stock:.1f} U** ({estado_txt}) | **${p_precio:.2f}**"):
                    with st.form(f"form_edit_{p_id}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            e_nombre = st.text_input("Nombre", value=p_nombre, key=f"nom_{p_id}")
                            e_cat = st.selectbox("Categoría", lista_cats_db, index=lista_cats_db.index(p_cat) if p_cat in lista_cats_db else 0, key=f"cat_{p_id}")
                            e_costo = parse_float(st.text_input("Costo Base ($)", value=str(p_costo), key=f"costo_{p_id}"))
                            e_ganancia = parse_float(st.text_input("Ganancia (%)", value=str(p_ganancia), key=f"gan_{p_id}"))
                            e_iva = st.checkbox("🏛️ ¿Aplica IVA (16%)?", value=p_iva, key=f"iva_{p_id}")
                            
                            m_dec = e_ganancia / 100
                            div = 1.0 - m_dec if m_dec < 1.0 else 0.01
                            p_sin_i = e_costo / div if div > 0 else e_costo
                            e_pv = p_sin_i * 1.16 if e_iva else p_sin_i
                            st.info(f"💵 **Venta Calc:** ${e_pv:.2f}")
                        with c2:
                            e_stock = parse_float(st.text_input("Stock Actual", value=str(p_stock), key=f"stk_{p_id}"))
                            e_motivo = st.text_input("Motivo ajuste", placeholder="Ej: Conteo...", key=f"mot_{p_id}")
                            e_es_cig = st.checkbox("📦 Caja / Detallado", value=p_es_cig, key=f"cig_{p_id}")
                            e_u_caja = parse_float(st.text_input("Unidades caja", value=str(p_u_caja), key=f"ucaj_{p_id}"))
                            e_obs = st.text_area("Observaciones", value=p_obs, key=f"obs_{p_id}")
                            
                        if st.form_submit_button("💾 Guardar Cambios", type="primary"):
                            cursor = conn.cursor()
                            cursor.execute("""UPDATE productos SET nombre=?, categoria=?, precio_venta=?, costo_insumo=?, porcentaje_ganancia=?, aplica_iva=?, stock=?, unidades_por_caja=?, es_cigarrillo=?, observaciones=? WHERE id=?""",
                                           (e_nombre, e_cat, round(e_pv, 2), e_costo, e_ganancia, 1 if e_iva else 0, e_stock, e_u_caja, 1 if e_es_cig else 0, e_obs, p_id))
                            if p_stock != e_stock:
                                cursor.execute("INSERT INTO historial_inventario (producto_id, producto_nombre, fecha, stock_anterior, stock_nuevo, motivo) VALUES (?, ?, ?, ?, ?, ?)",
                                               (p_id, e_nombre, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), p_stock, e_stock, e_motivo or "Ajuste"))
                            conn.commit()
                            st.success("✔️ Actualizado.")
                            st.rerun()

                    if st.checkbox(f"⚠️ Eliminar '{p_nombre}'", key=f"chk_del_{p_id}"):
                        if st.button(f"🗑️ Confirmar Eliminación", key=f"btn_del_{p_id}", type="primary"):
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM productos WHERE id = ?", (p_id,))
                            cursor.execute("DELETE FROM historial_inventario WHERE producto_id = ?", (p_id,))
                            conn.commit()
                            st.error("💥 Eliminado.")
                            st.rerun()
        else:
            st.info("Sin productos.")

    with tab_nuevo:
        st.subheader("➕ Nuevo Producto")
        with st.form("form_nuevo_prod_seguro"):
            c1, c2 = st.columns(2)
            with c1:
                nombre_n = st.text_input("Nombre")
                categoria_n = st.selectbox("Categoría", lista_cats_db or ["Otros"], key="cat_nuevo")
                costo_n = parse_float(st.text_input("Costo Base ($)", value="0.00", key="costo_nuevo"))
                ganancia_n = parse_float(st.text_input("Ganancia (%)", value="40.00", key="gan_nuevo"))
                iva_n = st.checkbox("🏛️ ¿Aplica IVA (16%)?", key="iva_nuevo")
                
                div_n = 1.0 - (ganancia_n / 100) if (ganancia_n / 100) < 1.0 else 0.01
                p_sin_iva_n = costo_n / div_n if div_n > 0 else costo_n
                precio_v_n = p_sin_iva_n * 1.16 if iva_n else p_sin_iva_n
                st.info(f"💵 **Precio Venta:** ${precio_v_n:.2f}")
            with c2:
                stock_n = parse_float(st.text_input("Stock Inicial", value="0", key="stock_nuevo"))
                obs_n = st.text_area("Observaciones", key="obs_nuevo")
                es_cig_n = st.checkbox("📦 ¿Se vende caja y suelto?", key="cig_nuevo")
                u_caja_n = parse_float(st.text_input("Unidades en caja", value="20", key="ucaj_nuevo"))
            
            if st.form_submit_button("💾 Guardar Producto", type="primary"):
                if nombre_n:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""INSERT INTO productos (nombre, categoria, precio_venta, costo_insumo, porcentaje_ganancia, aplica_iva, stock, unidades_por_caja, es_cigarrillo, observaciones) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                       (nombre_n, categoria_n, round(precio_v_n, 2), costo_n, ganancia_n, 1 if iva_n else 0, stock_n, u_caja_n, 1 if es_cig_n else 0, obs_n))
                        cursor.execute("INSERT INTO historial_inventario (producto_id, producto_nombre, fecha, stock_anterior, stock_nuevo, motivo) VALUES (?, ?, ?, ?, ?, ?)",
                                       (cursor.lastrowid, nombre_n, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0.0, stock_n, "Ingreso Inicial"))
                        conn.commit()
                        st.success("✔️ Registrado.")
                        st.rerun()
                    except Exception:
                        st.error("❌ Ya existe un producto con ese nombre.")
                else:
                    st.warning("⚠️ Ingresa un nombre.")

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
        for cat in lista_cats_db:
            st.markdown(f"- 🏷️ {cat}")

    with tab_pizarra:
        nota_texto = st.text_area("Nueva nota:")
        if st.button("📌 Publicar Nota"):
            if nota_texto:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO notas_generales (fecha, nota) VALUES (?, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), nota_texto))
                conn.commit()
                st.rerun()
        df_notas = pd.read_sql_query("SELECT id, fecha, nota FROM notas_generales ORDER BY id DESC", conn)
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
    df_prod = pd.read_sql_query("SELECT * FROM productos", conn)
    
    if df_prod.empty:
        st.warning("Inventario vacío.")
    else:
        with st.container(border=True):
            prod_nombre = st.selectbox("Producto", df_prod['nombre'].tolist())
            info_p = df_prod[df_prod['nombre'] == prod_nombre].iloc[0]
            stock_actual, es_cigarrillo = float(info_p['stock']), int(info_p['es_cigarrillo'] or 0)
            u_caja = float(info_p['unidades_por_caja'] or 1.0)
            
            if es_cigarrillo == 1:
                opcion_empaque = st.radio("Empaque", ["Unidad/Suelto", "Caja Cerrada"], horizontal=True)
                if opcion_empaque == "Unidad/Suelto" and u_caja > 0:
                    st.caption(f"Stock: {stock_actual:.1f} U | C/U: ${float(info_p['precio_venta']) / u_caja:.3f}")
                else:
                    st.caption(f"Stock: {stock_actual:.1f} U")
            else:
                opcion_empaque = "Normal"
                st.caption(f"Stock: {stock_actual:.1f} U")
            
            precio_defecto_usd = float(info_p['precio_venta'])
            if st.checkbox("Precio Manual"):
                precio_manual_bs = st.number_input("Precio Bs.", min_value=0.0, value=round(precio_defecto_usd * tasa_dolar, 2))
                precio_final = precio_manual_bs / tasa_dolar if tasa_dolar > 0 else 0.0
            else:
                precio_final = precio_defecto_usd
                st.text(f"Ref: ${precio_final:.2f}")
                
            cant_vender = st.number_input("Cantidad", min_value=1, value=1, step=1)
            
            if st.button("➕ Agregar al Carrito", type="primary"):
                if es_cigarrillo == 1 and opcion_empaque == "Caja Cerrada":
                    factor_stock, precio_ajustado, nombre_carrito = u_caja, precio_final, prod_nombre
                elif es_cigarrillo == 1:
                    factor_stock, precio_ajustado, nombre_carrito = 1.0, (precio_final / u_caja if u_caja > 0 else precio_final), f"{prod_nombre} (Suelto)"
                else:
                    factor_stock, precio_ajustado, nombre_carrito = 1.0, precio_final, prod_nombre
                    
                st.session_state.carrito.append({
                    'id': int(info_p['id']), 'nombre': nombre_carrito, 
                    'unidades_stock': cant_vender * factor_stock,
                    'cantidad_pantalla': cant_vender, 'precio_u': precio_ajustado, 'subtotal': cant_vender * precio_ajustado
                })
                st.success("¡Agregado!")
                st.rerun()

        if st.session_state.carrito:
            st.markdown("---")
            st.markdown("### 🛍️ Carrito Actual")
            carrito_actualizado = []
            for i, item in enumerate(st.session_state.carrito):
                with st.container(border=True):
                    st.markdown(f"**{item['nombre']}** — ${item['precio_u']:.3f} c/u")
                    nueva_cant = st.number_input("Cantidad", min_value=1, value=int(item['cantidad_pantalla']), key=f"cant_item_{i}")
                    sub_usd = nueva_cant * item['precio_u']
                    st.write(f"**Subtotal:** ${sub_usd:.2f} *({sub_usd * tasa_dolar:.2f} Bs.)*")
                    if not st.button("🗑️ Quitar", key=f"del_item_{i}"):
                        factor_u = item['unidades_stock'] / item['cantidad_pantalla'] if item['cantidad_pantalla'] > 0 else 1.0
                        item_modificado = item.copy()
                        item_modificado['cantidad_pantalla'] = nueva_cant
                        item_modificado['unidades_stock'] = nueva_cant * factor_u
                        item_modificado['subtotal'] = sub_usd
                        carrito_actualizado.append(item_modificado)
            st.session_state.carrito = carrito_actualizado
            
            if st.session_state.carrito:
                total_usd = sum([i['subtotal'] for i in st.session_state.carrito])
                st.markdown("---")
                col_usd, col_bs = st.columns(2)
                col_usd.metric("TOTAL NETO", f"${total_usd:.2f}")
                col_bs.metric("TOTAL BS", f"{total_usd * tasa_dolar:.2f} Bs.")
                
                with st.container(border=True):
                    st.subheader("💳 Cierre Financiero")
                    pago_mixto = st.checkbox("🔀 Pago fraccionado / mixto")
                    bloquear_reg = False
                    cliente_name = ""
                    
                    if not pago_mixto:
                        metodo_pago = st.selectbox("Método de Pago", ["Efectivo (Divisa/USD)", "Efectivo (Bolívares)", "Pago Móvil / Transferencia", "Punto de Venta (Tarjeta)", "Fiado (Crédito)", "Consumo Interno"])
                        if metodo_pago == "Fiado (Crédito)":
                            lista_deudores = pd.read_sql_query("SELECT DISTINCT cliente FROM deudas WHERE saldo_pendiente >= 0.01", conn)['cliente'].tolist()
                            sel_deudor = st.selectbox("Deudor", ["-- Seleccionar --", "➕ Registrar Nuevo"] + lista_deudores)
                            if sel_deudor == "➕ Registrar Nuevo":
                                cliente_name = st.text_input("Nombre del nuevo deudor:")
                            elif sel_deudor != "-- Seleccionar --":
                                cliente_name = sel_deudor
                        elif metodo_pago == "Punto de Venta (Tarjeta)":
                            cliente_name = st.text_input("Referencia / Tarjeta")
                        
                        m_ef_usd = total_usd if metodo_pago == "Efectivo (Divisa/USD)" else 0.0
                        m_ef_bs = (total_usd * tasa_dolar) if metodo_pago == "Efectivo (Bolívares)" else 0.0
                        m_pm = (total_usd * tasa_dolar) if metodo_pago == "Pago Móvil / Transferencia" else 0.0
                        m_ptv = (total_usd * tasa_dolar * 0.98) if metodo_pago == "Punto de Venta (Tarjeta)" else 0.0
                        monto_ingreso_caja = total_usd if metodo_pago != "Punto de Venta (Tarjeta)" else total_usd * 0.98
                        
                        if metodo_pago in ["Consumo Interno", "Fiado (Crédito)"]:
                            monto_ingreso_caja = 0.0
                            m_ef_usd = m_ef_bs = m_pm = m_ptv = 0.0
                            
                        metodo_final = metodo_pago
                        if metodo_pago == "Fiado (Crédito)" and not cliente_name:
                            st.warning("⚠️ Ingresa o selecciona un deudor.")
                            bloquear_reg = True
                    else:
                        p_ef_usd = st.number_input("Efectivo USD", min_value=0.0, value=0.0, key="m_usd")
                        p_ef_bs = st.number_input("Efectivo Bs", min_value=0.0, value=0.0, key="m_bs")
                        p_pm = st.number_input("Pago Móvil", min_value=0.0, value=0.0, key="m_pm")
                        p_ptv_neto = st.number_input("Punto Venta (Bruto)", min_value=0.0, value=0.0, key="m_ptv") * 0.98
                        
                        suma_usd = p_ef_usd + (p_ef_bs / tasa_dolar if tasa_dolar > 0 else 0) + (p_pm / tasa_dolar if tasa_dolar > 0 else 0) + (p_ptv_neto / tasa_dolar if tasa_dolar > 0 else 0)
                        dif = round(suma_usd - total_usd, 2)
                        if dif < -0.01:
                            st.warning(f"⚠️ Faltan ${abs(dif):.2f}")
                            bloquear_reg = True
                        else:
                            st.success(f"✅ Montos correctos. Vuelto: ${max(0.0, dif):.2f}")
                        m_ef_usd, m_ef_bs, m_pm, m_ptv = p_ef_usd, p_ef_bs, p_pm, p_ptv_neto
                        monto_ingreso_caja, metodo_final, cliente_name = total_usd, "Pago Mixto", ""

                    if st.button("🗑️ Cancelar"):
                        st.session_state.carrito = []
                        st.rerun()
                        
                    if st.button("✅ Registrar Venta", type="primary", disabled=bloquear_reg):
                        cursor = conn.cursor()
                        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("INSERT INTO ventas_maestro (fecha, subtotal, impuesto, total, metodo_pago, cliente, monto_efectivo_usd, monto_efectivo_bs, monto_pago_movil, monto_punto) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                       (ahora, total_usd, 0.0, monto_ingreso_caja, metodo_final, cliente_name, m_ef_usd, m_ef_bs, m_pm, m_ptv))
                        v_id = cursor.lastrowid
                        detalles_compra = ", ".join([f"{item['cantidad_pantalla']}x {item['nombre']}" for item in st.session_state.carrito])
                        
                        for item in st.session_state.carrito:
                            cursor.execute("INSERT INTO ventas_detalle (venta_id, producto_id, cantidad, precio_unitario, unidades_stock) VALUES (?, ?, ?, ?, ?)", 
                                           (v_id, item['id'], item['cantidad_pantalla'], item['precio_u'], item['unidades_stock']))
                            cursor.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (item['unidades_stock'], item['id']))
                            
                        if not pago_mixto and metodo_pago == "Fiado (Crédito)":
                            cursor.execute("SELECT id, detalles FROM deudas WHERE cliente = ? AND saldo_pendiente >= 0.01", (cliente_name,))
                            deuda_ex = cursor.fetchone()
                            if deuda_ex:
                                nuevos_det = f"{deuda_ex[1]} | + {detalles_compra}" if deuda_ex[1] else detalles_compra
                                cursor.execute("UPDATE deudas SET monto_total = monto_total + ?, saldo_pendiente = saldo_pendiente + ?, ultima_actualizacion = ?, detalles = ? WHERE id = ?",
                                               (total_usd, total_usd, ahora, nuevos_det, int(deuda_ex[0])))
                            else:
                                cursor.execute("INSERT INTO deudas (cliente, monto_total, saldo_pendiente, fecha_origen, ultima_actualizacion, detalles) VALUES (?, ?, ?, ?, ?, ?)",
                                               (cliente_name, total_usd, total_usd, ahora, ahora, detalles_compra))
                        conn.commit()
                        st.session_state.carrito = []
                        st.success("🎉 ¡Venta registrada!")
                        st.rerun()

# ==========================================
# MÓDULO: EGRESOS E IMPUESTOS
# ==========================================
elif modulo == "📉 Egresos e Impuestos":
    st.title("📉 Egresos e Impuestos")
    t1, t2 = st.tabs(["💸 Registrar Egreso", "🏛️ Impuestos"])
    with t1:
        with st.form("form_egresos"):
            tipo = st.selectbox("Tipo", ["Compra de Mercancía/Insumos", "Pago de Salarios", "Servicios Públicos", "Seguro de Punto de Venta", "Impuestos Alcaldía"])
            desc = st.text_input("Detalle / Proveedor")
            moneda = st.selectbox("Moneda", ["Dólares ($)", "Bolívares (Bs.)"])
            monto = st.number_input("Monto", min_value=0.0, format="%.2f")
            origen = st.selectbox("Origen", ["Efectivo USD", "Efectivo Bs.", "Banco / Cuenta Bs."])
            if st.form_submit_button("Registrar", type="primary"):
                if monto > 0:
                    m_usd = monto if moneda == "Dólares ($)" else monto / tasa_dolar
                    m_bs = monto * tasa_dolar if moneda == "Dólares ($)" else monto
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO egresos_maestro (fecha, proveedor, tipo_gasto, subtotal, porcentaje_impuesto, monto_impuesto, total, origen_fondo, monto_efectivo_usd, monto_efectivo_bs, monto_bancos_bs) VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?)",
                                   (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), desc, tipo, m_usd, m_usd, origen, m_usd if origen == "Efectivo USD" else 0, m_bs if origen == "Efectivo Bs." else 0, m_bs if origen == "Banco / Cuenta Bs." else 0))
                    conn.commit()
                    st.success("✔️ Egreso guardado.")
                    st.rerun()
                else:
                    st.error("Monto inválido.")
    with t2:
        dias = st.number_input("Días hacia atrás", min_value=1, value=7)
        fecha_corte = (datetime.now() - pd.Timedelta(days=dias)).strftime("%Y-%m-%d")
        v_per = pd.read_sql_query("SELECT SUM(total) as t FROM ventas_maestro WHERE fecha >= ? AND metodo_pago NOT IN ('Consumo Interno', 'Fiado (Crédito)')", conn, params=(fecha_corte,)).iloc[0]['t'] or 0.0
        c_per = pd.read_sql_query("""
            SELECT SUM(COALESCE(vd.unidades_stock, vd.cantidad) * (CASE WHEN p.es_cigarrillo = 1 AND p.unidades_por_caja > 0 THEN p.costo_insumo / p.unidades_por_caja ELSE p.costo_insumo END)) as c 
            FROM ventas_detalle vd 
            JOIN productos p ON vd.producto_id = p.id 
            JOIN ventas_maestro vm ON vd.venta_id = vm.id 
            WHERE vm.fecha >= ? AND vm.metodo_pago NOT IN ('Consumo Interno', 'Fiado (Crédito)')
        """, conn, params=(fecha_corte,)).iloc[0]['c'] or 0.0
        gan_neta = v_per - c_per
        porc = st.slider("Impuesto Municipal (%)", 1.0, 5.0, 2.0, 0.5)
        imp = gan_neta * (porc / 100) if gan_neta > 0 else 0.0
        st.success(f"**Ganancia Neta:** ${gan_neta:.2f} | **A Pagar:** ${imp:.2f}")
        if st.button("🏛️ Pagar Alcaldía", disabled=(imp <= 0), type="primary"):
            cursor = conn.cursor()
            cursor.execute("INSERT INTO egresos_maestro (fecha, proveedor, tipo_gasto, subtotal, porcentaje_impuesto, monto_impuesto, total, origen_fondo, monto_efectivo_usd, monto_efectivo_bs, monto_bancos_bs) VALUES (?, 'Alcaldía', 'Impuestos Alcaldía', ?, 0, 0, ?, 'Banco Bs.', 0, 0, ?)",
                           (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), imp, imp, imp * tasa_dolar))
            conn.commit()
            st.rerun()

# ==========================================
# MÓDULO: FINANZAS Y CAPITAL
# ==========================================
elif modulo == "💰 Finanzas y Capital":
    st.title("💰 Finanzas y Capital")
    if st.text_input("🔒 Contraseña:", type="password") != "1234":
        st.stop()
    st.success("🔓 Acceso autorizado.")
    st.markdown("---")
    
    movs = pd.read_sql_query("SELECT tipo, efectivo_usd, efectivo_bs, bancos_bs FROM movimientos_capital", conn)
    ef_u = ef_b = ban_b = 0.0
    for _, r in movs.iterrows():
        f_u, f_eb, f_bb = float(r['efectivo_usd']), float(r['efectivo_bs']), float(r['bancos_bs'])
        if r['tipo'] == 'Inyección de Capital':
            ef_u += f_u; ef_b += f_eb; ban_b += f_bb
        else:
            ef_u -= f_u; ef_b -= f_eb; ban_b -= f_bb
            
    v = pd.read_sql_query("SELECT monto_efectivo_usd, monto_efectivo_bs, monto_pago_movil, monto_punto FROM ventas_maestro WHERE metodo_pago != 'Consumo Interno'", conn)
    e = pd.read_sql_query("SELECT monto_efectivo_usd, monto_efectivo_bs, monto_bancos_bs FROM egresos_maestro", conn)
    
    tot_ef_u = ef_u + v['monto_efectivo_usd'].sum() - e['monto_efectivo_usd'].sum()
    tot_ef_b = ef_b + v['monto_efectivo_bs'].sum() - e['monto_efectivo_bs'].sum()
    tot_ban = ban_b + (v['monto_pago_movil'] + v['monto_punto']).sum() - e['monto_bancos_bs'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Ef. USD", f"${tot_ef_u:,.2f}")
    c2.metric("💵 Ef. Bs", f"{tot_ef_b:,.2f} Bs.")
    c3.metric("🏦 Bancos", f"{tot_ban:,.2f} Bs.")
    
    st.markdown("---")
    with st.form("form_mov"):
        t_mov = st.selectbox("Operación", ["Inyección de Capital", "Retiro de Capital"])
        mu = st.number_input("Efectivo USD", min_value=0.0)
        mb = st.number_input("Efectivo Bs", min_value=0.0)
        mban = st.number_input("Banco Bs", min_value=0.0)
        concepto = st.text_input("Concepto")
        if st.form_submit_button("Guardar", type="primary"):
            if mu > 0 or mb > 0 or mban > 0:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO movimientos_capital (fecha, tipo, efectivo_usd, efectivo_bs, bancos_bs, concepto) VALUES (?, ?, ?, ?, ?, ?)",
                               (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), t_mov, mu, mb, mban, concepto or t_mov))
                conn.commit()
                st.success("✔️ Guardado.")
                st.rerun()

# ==========================================
# MÓDULO: DEUDORES (FIADOS CORREGIDO)
# ==========================================
elif modulo == "👥 Control de Deudores (Fiados)":
    st.title("👥 Cuentas por Cobrar (Fiados)")
    df_deudas = pd.read_sql_query("SELECT id, cliente, saldo_pendiente, detalles FROM deudas WHERE saldo_pendiente >= 0.01", conn)
    
    if not df_deudas.empty:
        for _, row in df_deudas.iterrows():
            d_id, cliente_actual, saldo_usd, detalles_deuda = int(row['id']), row['cliente'], float(row['saldo_pendiente']), row['detalles']
            with st.expander(f"👤 **{cliente_actual}** — Deuda: **${saldo_usd:.2f}** *({saldo_usd * tasa_dolar:,.2f} Bs.)*"):
                st.markdown(f"**🛒 Artículos / Cuenta Activa:**\n\n {detalles_deuda if detalles_deuda else 'Sin detalle registrado.'}")
                st.markdown("---")
                
                monto_abono = st.number_input("Monto a abonar ($)", min_value=0.01, max_value=saldo_usd, value=saldo_usd, key=f"abono_{d_id}")
                metodo_abono = st.selectbox("Método de Abono", ["Efectivo (Divisa/USD)", "Efectivo (Bolívares)", "Pago Móvil / Transferencia", "Punto de Venta (Tarjeta)"], key=f"met_abono_{d_id}")
                
                if st.button("✅ Procesar Abono", key=f"btn_abono_{d_id}", type="primary"):
                    cursor = conn.cursor()
                    nuevo_bal = round(saldo_usd - monto_abono, 2)
                    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    if nuevo_bal < 0.01:
                        cursor.execute("DELETE FROM deudas WHERE id = ?", (d_id,))
                    else:
                        cursor.execute("UPDATE deudas SET saldo_pendiente = ?, ultima_actualizacion = ? WHERE id = ?", (nuevo_bal, ahora, d_id))
                    
                    m_u = monto_abono if metodo_abono == "Efectivo (Divisa/USD)" else 0.0
                    m_b = (monto_abono * tasa_dolar) if metodo_abono == "Efectivo (Bolívares)" else 0.0
                    m_pm = (monto_abono * tasa_dolar) if metodo_abono == "Pago Móvil / Transferencia" else 0.0
                    m_ptv = (monto_abono * tasa_dolar * 0.98) if metodo_abono == "Punto de Venta (Tarjeta)" else 0.0
                    ing_caja = monto_abono if metodo_abono != "Punto de Venta (Tarjeta)" else monto_abono * 0.98
                    
                    cursor.execute("INSERT INTO ventas_maestro (fecha, subtotal, impuesto, total, metodo_pago, cliente, monto_efectivo_usd, monto_efectivo_bs, monto_pago_movil, monto_punto) VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?)",
                                   (ahora, monto_abono, ing_caja, f"Abono - {metodo_abono}", f"Abono Deuda - {cliente_actual}", m_u, m_b, m_pm, m_ptv))
                    conn.commit()
                    st.success("✅ Abono procesado con éxito.")
                    st.rerun()
    else:
        st.success("🎉 ¡Todos al día!")

# ==========================================
# MÓDULO: DASHBOARD Y CIERRE
# ==========================================
elif modulo == "📊 Dashboard / Cierre Caja":
    st.title("📊 Panel de Control y Cierre de Caja")
    fecha_sel = st.date_input("📅 Día:", value=datetime.now())
    hoy = fecha_sel.strftime("%Y-%m-%d")
    param_hoy = f"{hoy}%"
    
    df_v = pd.read_sql_query("SELECT * FROM ventas_maestro WHERE fecha LIKE ?", conn, params=(param_hoy,))
    df_e = pd.read_sql_query("SELECT total FROM egresos_maestro WHERE fecha LIKE ?", conn, params=(param_hoy,))
    
    # Consulta de costos corregida con unidades proporcionales y excluyendo abonos/consumo interno
    df_c = pd.read_sql_query("""
        SELECT SUM(
            COALESCE(vd.unidades_stock, vd.cantidad) * (
                CASE 
                    WHEN p.es_cigarrillo = 1 AND p.unidades_por_caja > 0 THEN p.costo_insumo / p.unidades_por_caja 
                    ELSE p.costo_insumo 
                END
            )
        ) as costo_total 
        FROM ventas_detalle vd 
        JOIN productos p ON vd.producto_id = p.id 
        JOIN ventas_maestro vm ON vd.venta_id = vm.id 
        WHERE vm.fecha LIKE ? 
          AND vm.metodo_pago != 'Consumo Interno' 
          AND vm.metodo_pago NOT LIKE 'Abono%'
    """, conn, params=(param_hoy,))
    
    if not df_v.empty:
        df_v_com = df_v[(~df_v['metodo_pago'].str.startswith('Abono', na=False)) & (df_v['metodo_pago'] != 'Consumo Interno')]
        df_ab = df_v[df_v['metodo_pago'].str.startswith('Abono', na=False)]
    else:
        df_v_com = df_ab = pd.DataFrame(columns=['subtotal', 'total'])
        
    val_desp = df_v_com['subtotal'].sum() if not df_v_com.empty else 0.0
    costo_tot = df_c.iloc[0]['costo_total'] if not df_c.empty and pd.notna(df_c.iloc[0]['costo_total']) else 0.0
    egresos_h = df_e['total'].sum() if not df_e.empty else 0.0
    com_punto = df_v_com['subtotal'].sum() - df_v_com['total'].sum()
    
    ganancia_neta = val_desp - com_punto - costo_tot - egresos_h
    caja_final = (df_v_com['total'].sum() if not df_v_com.empty else 0.0) + (df_ab['total'].sum() if not df_ab.empty else 0.0) - egresos_h

    st.markdown("### 📈 Rendimiento del Día")
    st.metric("📦 Valor Despachado", f"${val_desp:.2f}")
    st.metric("📉 Costo de Mercancía Vendida", f"${costo_tot:.2f}")
    st.metric("📤 Egresos", f"${egresos_h:.2f}")
    
    if ganancia_neta >= 0:
        st.metric("💰 GANANCIA REAL", f"${ganancia_neta:.2f}")
    else:
        st.metric("🚨 PÉRDIDA", f"${ganancia_neta:.2f}", delta_color="inverse")
        
    st.markdown("---")
    st.metric("⚖️ BALANCE ESPERADO EN CAJA", f"${caja_final:.2f}")

    if st.button("🏁 EJECUTAR CIERRE DE CAJA DIARIO", type="primary"):
        cursor = conn.cursor()
        ef_u = df_v['monto_efectivo_usd'].sum() if 'monto_efectivo_usd' in df_v.columns else 0.0
        ef_b = df_v['monto_efectivo_bs'].sum() if 'monto_efectivo_bs' in df_v.columns else 0.0
        ptv = df_v['monto_punto'].sum() if 'monto_punto' in df_v.columns else 0.0
        pm = df_v['monto_pago_movil'].sum() if 'monto_pago_movil' in df_v.columns else 0.0
        
        cursor.execute("INSERT INTO cierres_diarios (fecha, ganancia_neta, efectivo_usd, efectivo_bs, punto_neto, pago_movil_transferencia, balance_total_usd) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (hoy, ganancia_neta, ef_u, ef_b, ptv, pm, caja_final))
        conn.commit()
        st.success("🔒 ¡Cierre guardado!")
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
        st.download_button("📊 Descargar Excel", output.getvalue(), f"Cierres_{datetime.now().strftime('%Y%m%d')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    else:
        st.info("Sin cierres.")

if conn:
    conn.close()
