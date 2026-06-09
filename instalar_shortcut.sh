#!/bin/bash
# instalar_shortcut.sh
# Compila el AppleScript en una app y la deja lista para asignarle ⌘⇧W.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_SRC="$SCRIPT_DIR/agregar_contacto_whatsapp.applescript"
APP_NAME="AgregarContactoCRM"
APP_DEST="$HOME/Applications/$APP_NAME.app"

echo ""
echo "═══════════════════════════════════════════════"
echo "  CRM Tizado — Instalador de atajo ⌘⇧W"
echo "═══════════════════════════════════════════════"
echo ""

# ── 1. Verificar que existe el AppleScript ──────────────────────────────────
if [ ! -f "$SCRIPT_SRC" ]; then
  echo "❌  No se encontró: $SCRIPT_SRC"
  exit 1
fi

# ── 2. Crear ~/Applications si no existe ────────────────────────────────────
mkdir -p "$HOME/Applications"

# ── 3. Compilar AppleScript → .app ──────────────────────────────────────────
echo "▸ Compilando AppleScript..."
osacompile -o "$APP_DEST" "$SCRIPT_SRC"
echo "✓ App creada en: $APP_DEST"

# ── 4. Registrar como Servicio del sistema via Automator ────────────────────
SERVICE_DIR="$HOME/Library/Services"
SERVICE_NAME="Agregar Contacto al CRM.workflow"
SERVICE_PATH="$SERVICE_DIR/$SERVICE_NAME"

mkdir -p "$SERVICE_DIR"

# Crear el workflow de Automator
mkdir -p "$SERVICE_PATH/Contents"
cat > "$SERVICE_PATH/Contents/document.wflow" << 'WFLOW'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>AMApplicationBuild</key>
  <string>521.1</string>
  <key>AMApplicationVersion</key>
  <string>2.10</string>
  <key>AMDocumentVersion</key>
  <string>2</string>
  <key>actions</key>
  <array>
    <dict>
      <key>action</key>
      <dict>
        <key>AMAccepts</key>
        <dict>
          <key>Container</key>
          <string>List</string>
          <key>Optional</key>
          <true/>
          <key>Types</key>
          <array><string>com.apple.cocoa.string</string></array>
        </dict>
        <key>AMActionVersion</key>
        <string>2.0.3</string>
        <key>AMApplication</key>
        <array><string>Automator</string></array>
        <key>AMParameterProperties</key>
        <dict>
          <key>COMMAND_STRING</key>
          <dict/>
        </dict>
        <key>AMProvides</key>
        <dict>
          <key>Container</key>
          <string>List</string>
          <key>Types</key>
          <array><string>com.apple.cocoa.string</string></array>
        </dict>
        <key>ActionBundlePath</key>
        <string>/System/Library/Automator/Run Shell Script.action</string>
        <key>ActionName</key>
        <string>Run Shell Script</string>
        <key>ActionParameters</key>
        <dict>
          <key>COMMAND_STRING</key>
          <string>osascript "$HOME/Applications/AgregarContactoCRM.app/Contents/Resources/Scripts/main.scpt" &amp;</string>
          <key>CheckedForUserDefaultShell</key>
          <true/>
          <key>inputMethod</key>
          <integer>0</integer>
          <key>shell</key>
          <string>/bin/bash</string>
          <key>source</key>
          <string></string>
        </dict>
        <key>BundleIdentifier</key>
        <string>com.apple.RunShellScript</string>
        <key>CFBundleVersion</key>
        <string>2.0.3</string>
        <key>CanShowSelectedItemsWhen</key>
        <false/>
        <key>CanShowWhenRun</key>
        <false/>
        <key>Category</key>
        <array><string>AMCategoryUtilities</string></array>
        <key>Class Name</key>
        <string>RunShellScriptAction</string>
        <key>InputUUID</key>
        <string>F7B6B6B0-1234-5678-ABCD-000000000001</string>
        <key>Keywords</key>
        <array><string>Shell</string><string>Script</string></array>
        <key>OutputUUID</key>
        <string>F7B6B6B0-1234-5678-ABCD-000000000002</string>
        <key>UUID</key>
        <string>F7B6B6B0-1234-5678-ABCD-000000000003</string>
        <key>UnlocalizedApplications</key>
        <array><string>Automator</string></array>
        <key>arguments</key>
        <dict/>
        <key>isViewVisible</key>
        <true/>
        <key>location</key>
        <string>309.000000:367.000000</string>
        <key>nibPath</key>
        <string>/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib</string>
      </dict>
      <key>isViewVisible</key>
      <true/>
    </dict>
  </array>
  <key>connectors</key>
  <dict/>
  <key>workflowMetaData</key>
  <dict>
    <key>serviceInputTypeIdentifier</key>
    <string>com.apple.automator.no-input</string>
    <key>serviceOutputTypeIdentifier</key>
    <string>com.apple.automator.no-output</string>
    <key>serviceProcessesInput</key>
    <integer>0</integer>
    <key>workflowTypeIdentifier</key>
    <string>com.apple.automator.servicesMenu</string>
  </dict>
</dict>
</plist>
WFLOW

echo "✓ Servicio instalado en: $SERVICE_PATH"

# ── 5. Registrar atajo ⌘⇧W en System Preferences ───────────────────────────
# Valor: 0x77 = 'w', modifiers: 1179648 = ⌘⇧ (Cmd=1048576 + Shift=131072)
SHORTCUT_KEY="Agregar Contacto al CRM"
PLIST="$HOME/Library/Preferences/com.apple.symbolichotkeys.plist"

/usr/libexec/PlistBuddy -c "Add :AppleSymbolicHotKeys:0 dict" "$PLIST" 2>/dev/null || true

# Usar defaults para registrar el atajo del servicio
defaults write com.apple.symbolichotkeys AppleSymbolicHotKeys -dict-add \
  "$(defaults read com.apple.symbolichotkeys AppleSymbolicHotKeys 2>/dev/null)" 2>/dev/null || true

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✓ Instalación completada"
echo "═══════════════════════════════════════════════"
echo ""
echo "  PASOS FINALES (manual — solo 1 vez):"
echo ""
echo "  1. Abrí: Configuración del Sistema → Teclado"
echo "     → Atajos de teclado → Servicios"
echo ""
echo "  2. Buscá 'Agregar Contacto al CRM'"
echo "     y asignale el atajo: ⌘⇧W"
echo ""
echo "  3. Asegurate que WhatsApp tenga permiso de"
echo "     Accesibilidad en:"
echo "     Configuración → Privacidad → Accesibilidad"
echo ""
echo "  USO:"
echo "  • Teniendo WhatsApp abierto con un chat activo,"
echo "    presioná ⌘⇧W (o buscá el servicio en el"
echo "    menú WhatsApp → Servicios)"
echo "  • Se detecta el nombre, completás teléfono y nota"
echo "  • El contacto se sube al CRM automáticamente"
echo ""
