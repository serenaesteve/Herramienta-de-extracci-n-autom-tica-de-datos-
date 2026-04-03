# DocExtract 📄

Herramienta de extracción automática de datos desde documentos PDF e imágenes.
Usa **Ollama** (IA local) para estructurar los datos sin enviarlos a la nube.

## Características

- **Login y registro** con sesiones seguras
- **Tipos de documento**: Factura, Contrato, Albarán, DNI, Presupuesto, Ticket, Nómina, Libre
- **OCR automático**: texto digital y documentos escaneados
- **IA local con Ollama**: sin costes, sin datos en la nube
- **Historial completo** de todas las extracciones
- **Exportación** a JSON y CSV
- **Diseño editorial oscuro** con tipografía Syne + DM Mono

---

## Requisitos previos

### 1. Tesseract OCR
```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-spa

# macOS
brew install tesseract tesseract-lang
```

### 2. Ollama
```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Descargar modelo (llama3 recomendado)
ollama pull llama3

# Verificar que está corriendo
ollama serve
```

---

## Instalación

```bash
# Clonar o copiar el proyecto
cd docextract

# Crear entorno virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar
python app.py
```

Abre **http://localhost:5000** en tu navegador.

---

## Configuración

En `app.py` puedes cambiar:

```python
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"   # o "mistral", "llama3.2", etc.
```

---

## Estructura del proyecto

```
docextract/
├── app.py                  # Backend Flask principal
├── requirements.txt
├── README.md
├── uploads/                # Archivos temporales (se borran tras procesar)
├── instance/
│   └── docextract.db       # Base de datos SQLite (auto-generada)
└── templates/
    ├── auth.html           # Login y registro
    ├── dashboard.html      # Interfaz principal de extracción
    ├── detail.html         # Vista detalle de una extracción
    └── profile.html        # Perfil y ajustes de cuenta
```

---

## Modelos Ollama recomendados

| Modelo | Velocidad | Calidad | RAM mínima |
|--------|-----------|---------|------------|
| `llama3` | Media | Alta | 8 GB |
| `llama3.2` | Rápida | Alta | 4 GB |
| `mistral` | Media | Alta | 6 GB |
| `phi3` | Muy rápida | Media | 4 GB |

---

## Tipos de extracción

| Tipo | Campos extraídos |
|------|-----------------|
| Factura | Número, fecha, emisor, cliente, NIF, base, IVA, total, IBAN |
| Contrato | Partes, fechas, objeto, importe, cláusulas |
| Albarán | Número, proveedor, destinatario, artículos, cantidades |
| DNI/ID | Nombre, apellidos, número, fechas, lugar nacimiento |
| Presupuesto | Número, partidas, IVA, descuento, total |
| Ticket | Establecimiento, artículos, total, forma de pago |
| Nómina | Empresa, trabajador, salario bruto/neto, retenciones |
| Libre | Los campos que tú especifiques |
