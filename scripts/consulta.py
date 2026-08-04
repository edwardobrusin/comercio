import requests
import pandas as pd
import time
import glob
import os
from tqdm import tqdm
import datetime
from pathlib import Path

def get_census_data(year, flow, api_key, cty_code):
    all_months = []
    
    # Definir variables según el flujo para evitar errores 400
    if flow == 'imports':
        commodity_var = "I_COMMODITY"
        desc_var = "I_COMMODITY_LDESC"
        value_var = "GEN_VAL_MO"
    else: # exports
        commodity_var = "E_COMMODITY"
        desc_var = "E_COMMODITY_LDESC"
        value_var = "ALL_VAL_MO"

    # tqdm encapsula el rango para mostrar el avance mes a mes en la terminal
    for m in tqdm(range(1, 13), desc=f"Consultando {flow.upper()} {year}", leave=False, ncols=90, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}'):
        month = f"{m:02d}"
        
        # URL construida con variables correctas
        url = (f"https://api.census.gov/data/timeseries/intltrade/{flow}/statehs?"
               f"COMM_LVL=HS6&YEAR={year}&MONTH={month}&"
               f"get=STATE,CTY_CODE,{commodity_var},{desc_var},{value_var}&"
               f"CTY_CODE={cty_code}&key={api_key}")
        
        intentos = 0
        exito = False
        while intentos < 3 and not exito:
            try:
                # Agregamos timeout para evitar que se quede colgado indefinidamente
                response = requests.get(url, timeout=15)
                
                if response.status_code == 200:
                    data = response.json()
                    df = pd.DataFrame(data[1:], columns=data[0])
                    df['month'] = month
                    all_months.append(df)
                    exito = True
                elif response.status_code == 204:
                    exito = True # Es normal para meses futuros
                else:
                    print(f"Error {response.status_code} en {flow} {year}-{month}: {response.text}")
                    exito = True # Salir del bucle si es un error distinto a conexión
            except requests.exceptions.RequestException as e:
                intentos += 1
                time.sleep(2) # Esperar antes de reintentar
                if intentos == 3:
                    print(f"\nFallo de conexión tras 3 intentos en {flow} {year}-{month}: {e}")
        
        time.sleep(0.5)

    return pd.concat(all_months, ignore_index=True) if all_months else None

def procesar_y_limpiar_datos(df, flujo, anio):
    """Aplica la limpieza estructural y de tipos en memoria (Códigos 1 y 2 unidos)."""
    # 1. Renombrar columnas dinámicamente
    renombrar_cols = {}
    for col in df.columns:
        if col.endswith('COMMODITY'): renombrar_cols[col] = 'COMMODITY'
        elif col.endswith('COMMODITY_LDESC'): renombrar_cols[col] = 'DESC'
        elif col in ['GEN_VAL_MO', 'ALL_VAL_MO']: renombrar_cols[col] = 'VALOR'
        elif col == 'YEAR': renombrar_cols[col] = 'year'
        elif col == 'MONTH' and 'month' not in df.columns: renombrar_cols[col] = 'month'
    
    df = df.rename(columns=renombrar_cols)
    
    # 2. Generar columnas faltantes (flow, year y Chapter)
    df['flow'] = flujo
    if 'year' not in df.columns:
        df['year'] = anio
        
    df['COMMODITY'] = df['COMMODITY'].astype(str).str.zfill(6)
    df['Chapter'] = df['COMMODITY'].str[:2]
    
    # 3. Filtrado de esquema estricto (Auditoría temprana)
    columnas_req = ['STATE', 'COMMODITY', 'DESC', 'VALOR', 'month', 'flow', 'year', 'Chapter']
    df = df[columnas_req]
    
    # 4. Limpieza de tipos y formatos forzados para Streamlit/DuckDB
    df['Chapter'] = df['Chapter'].astype(str).str.zfill(2)
    df['VALOR'] = pd.to_numeric(df['VALOR'], errors='coerce').fillna(0).astype('float64')
    df['year'] = pd.to_numeric(df['year'], errors='coerce').fillna(0).astype(int)
    df['month'] = pd.to_numeric(df['month'], errors='coerce').fillna(0).astype(int)
    
    # 5. Pre-concatenar descripciones y limpiar basura/totales pre-calculados
    df['COM_DESC'] = df['COMMODITY'] + " - " + df['DESC'].astype(str)
    df = df[~df['COMMODITY'].isin(['ALL', 'nan', 'NaN', 'None', '<NA>'])]
    
    return df

def obtener_anios_a_procesar(ruta_salida, carpeta, flujo):
    """Revisa los meses disponibles y aplica la regla de 3 meses o reanuda si hay brechas por socio y flujo."""
    archivos = glob.glob(os.path.join(ruta_salida, carpeta, f"census_{flujo}_*.parquet"))
    current_year = datetime.datetime.now().year
    
    if not archivos:
        # Si está vacío, extraemos el histórico completo
        return list(range(2010, current_year + 1))
    
    anios_existentes = [int(os.path.basename(f).split('_')[2].replace('.parquet', '')) for f in archivos]
    max_year = max(anios_existentes)
    
    # Si el último año descargado es menor al actual, devolvemos el rango faltante completo
    if max_year < current_year:
        print(f"⚠️ Descarga incompleta en {carpeta.upper()} - {flujo.upper()}. Reanudando desde {max_year} hasta {current_year}.")
        return list(range(max_year, current_year + 1))
    
    archivo_reciente = os.path.join(ruta_salida, carpeta, f"census_{flujo}_{max_year}.parquet")
    try:
        df_recent = pd.read_parquet(archivo_reciente)
        max_month = df_recent['month'].max()
        
        # Regla de actualización dinámica
        if max_month <= 3:
            return [max_year - 1, max_year]
        return [max_year]
    except Exception as e:
        print(f"⚠️ Error leyendo histórico en {carpeta.upper()} - {flujo.upper()} ({e}). Consultando únicamente {max_year}.")
        return [max_year]

# ==========================================
# EJECUCIÓN PRINCIPAL DEL PIPELINE
# ==========================================
API_KEY = "c97f835eb59de83d02f041fc508b0a5a9a6eb298"
RUTA_SALIDA = Path("data/intermediate")

# Parámetros correctos para separar el país en la API
config_socios = {
    "mexico": "2010",
    "total": "-"
}

for carpeta, cty_code in config_socios.items():
    carpeta_destino = RUTA_SALIDA / carpeta
    carpeta_destino.mkdir(parents=True, exist_ok=True)
    
    for f in ["imports", "exports"]:
        # Evaluamos los años necesarios de forma independiente para CADA carpeta y CADA flujo
        anios_objetivo = obtener_anios_a_procesar(RUTA_SALIDA, carpeta, f)
        print(f"🔄 Años a procesar para {carpeta.upper()} - {f.upper()}: {anios_objetivo}")
        
        for y in anios_objetivo:
            y_str = str(y)
            print(f"📥 Extrayendo {f.upper()} para {carpeta.upper()} ({y_str})...")
            
            # 1. Extracción
            df_year = get_census_data(y_str, f, API_KEY, cty_code)
            
            if df_year is not None and not df_year.empty:
                # 2. Transformación en memoria
                df_limpio = procesar_y_limpiar_datos(df_year, f, y)
                
                # 3. Carga optimizada
                filename = carpeta_destino / f"census_{f}_{y_str}.parquet"
                df_limpio.to_parquet(filename, index=False, engine='pyarrow')
                print(f"✅ Archivo estructurado y listo: {filename}")
            else:
                print(f"⚠️ No se encontraron datos para {carpeta} {f} {y_str}. Omitido.")
                
print("🚀 Proceso ETL finalizado.")