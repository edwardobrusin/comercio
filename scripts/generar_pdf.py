from playwright.sync_api import sync_playwright
import time
import os
import zipfile

# Diccionario de Secciones y Carpetas
SECCIONES = {
    "Sección I: Animales Vivos y Productos": "comercio_sec_I",
    "Sección II: Productos Vegetales": "comercio_sec_II"
}

# Lista de estados de EE. UU.
US_STATES = [
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
    'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
    'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
    'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
    'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
    'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
    'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
    'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
    'West Virginia', 'Wisconsin', 'Wyoming'
]

def generar_fichas_masivas(url="http://localhost:8501", zip_name="fichas_comercio_us.zip"):
    print("\n¿Qué acción deseas realizar?")
    print("1. Retomar (solo generar PDFs faltantes)")
    print("2. Actualizar (reescribir todos los PDFs)")
    opcion = input("Ingresa 1 o 2: ").strip()
    modo = "retomar" if opcion == "1" else "actualizar"
    print(f"\nModo seleccionado: {modo.upper()}")

    # 1. Crear los directorios principales si no existen
    for carpeta in SECCIONES.values():
        os.makedirs(carpeta, exist_ok=True)
        print(f"📁 Directorio destino preparado: {carpeta}/")

    with sync_playwright() as p:
        print("🤖 Iniciando navegador Chromium (Headless)...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1300, "height": 1080},
            device_scale_factor=1
        )
        page = context.new_page()

        # 2. Iterar sobre cada sección y cada estado
        total_fichas = len(SECCIONES) * len(US_STATES)
        contador = 1
        
        for sec_name, folder_name in SECCIONES.items():
            print(f"\n==================================================")
            print(f"📂 PROCESANDO SECCIÓN: {sec_name}")
            print(f"==================================================")
            
            for estado in US_STATES:
                output_path = os.path.join(folder_name, f"{estado}.pdf")
                
                if modo == "retomar" and os.path.exists(output_path):
                    print(f"\n[{contador}/{total_fichas}] ⏭️ Saltando: {estado} ({folder_name}) - PDF ya existe.")
                    contador += 1
                    continue

                print(f"\n[{contador}/{total_fichas}] Procesando: {estado} ({folder_name})...")
                
                # Navegamos a la app fresca
                page.goto(url, wait_until="domcontentloaded")
                
                # Esperamos a que el menú lateral esté visible
                page.wait_for_selector('[data-testid="stSidebar"]', state="visible", timeout=60000)
                
                # -- PASO A: SELECCIONAR SECCIÓN HTS --
                print("      Seleccionando Filtro HTS...")
                # Clickeamos el selectbox (Streamlit usa data-baseweb="select" para los dropdowns)
                page.locator('[data-baseweb="select"]').first.click()
                # Seleccionamos la opción correcta de la lista desplegable
                page.locator('li[role="option"]').get_by_text(sec_name, exact=True).click()
                time.sleep(1) # Pequeña pausa para que reaccione Streamlit
                
                # -- PASO B: SELECCIONAR ESTADO --
                print(f"      Haciendo clic en el estado: {estado}...")
                boton_estado = page.locator('[data-testid="stSidebar"] button').get_by_text(estado, exact=True)
                boton_estado.click()
                
                print("      Esperando procesamiento de datos y gráficas...")
                # TRUCO: Esperamos el H1 que confirma el estado y la P que confirma la sección activa
                page.wait_for_selector(f'h1:has-text("Análisis Comercial: {estado}")', state="visible", timeout=60000)
                page.wait_for_selector(f'p:has-text("Filtro Activo: {sec_name}")', state="visible", timeout=60000)
                
                # NUEVA LÓGICA DE ESPERA: Garantiza que Streamlit termine de procesar toda la página
                # 1. Esperamos a que el título de la última gráfica esté visible en el DOM
                page.wait_for_selector('h4:has-text("4. Top 10 Subpartidas Destinadas a México")', state="visible", timeout=60000)
                # 2. Esperamos a que el widget de "Running..." (arriba a la derecha) desaparezca nativamente
                page.locator('[data-testid="stStatusWidget"]').wait_for(state="hidden", timeout=60000)
                # 3. Nos aseguramos de que no haya peticiones de red pendientes
                page.wait_for_load_state("networkidle")
                
                time.sleep(1.5) # Breve pausa exclusiva para que las animaciones CSS terminen de extenderse
                
                print("      Inyectando CSS de limpieza y liberando lienzo...")
                css_limpieza = """
                    [data-testid="stSidebar"], header[data-testid="stHeader"], footer, .stAppDeployButton, #MainMenu {     
                        display: none !important; 
                    }
                    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main {
                        height: auto !important; min-height: 100% !important; overflow: visible !important; position: static !important;
                    }
                    [data-testid="stAppViewBlockContainer"], .block-container, [data-testid="block-container"] {
                        max-width: 100% !important; padding: 2rem !important; margin: 0 !important;
                    }
                    .stApp { background-color: #F8FAFC !important; }
                """
                page.add_style_tag(content=css_limpieza)
                time.sleep(2) # Reflow del DOM

                # Calcular altura real
                altura_total = page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, document.body.offsetHeight)")
                ancho_fijo = 1300

                # 3. Generar y guardar el PDF en su respectiva carpeta
                page.pdf(
                    path=output_path,
                    print_background=True,
                    width=f"{ancho_fijo}px",
                    height=f"{altura_total + 50}px"
                )
                print(f"      ✅ Guardado: {output_path}")
                contador += 1

        browser.close()
        
    # 4. Compresión automática de ambas carpetas en un archivo .zip
    print(f"\n📦 Empaquetando y comprimiendo carpetas en {zip_name} al máximo nivel...")
    try:
        with zipfile.ZipFile(zip_name, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
            for carpeta in SECCIONES.values():
                for root, _, files in os.walk(carpeta):
                    for file in files:
                        if file.endswith('.pdf'):
                            file_path = os.path.join(root, file)
                            # Conservamos la estructura de la carpeta dentro del ZIP (ej: comercio_sec_I/Texas.pdf)
                            arcname = os.path.join(carpeta, file)
                            zipf.write(file_path, arcname=arcname)
        print(f"✅ ¡Éxito! Archivo ZIP generado con máxima compresión en: {zip_name}")
    except Exception as e:
        print(f"❌ Error al generar el archivo ZIP: {e}")

    print("\n🎉 ¡Proceso masivo completado de principio a fin!")

if __name__ == "__main__":
    generar_fichas_masivas(url="http://localhost:8501")