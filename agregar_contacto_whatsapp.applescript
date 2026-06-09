-- agregar_contacto_whatsapp.applescript
-- Detecta el contacto activo en WhatsApp y lo agrega al CRM de Tizado.

property SHEETS_URL : "https://script.google.com/macros/s/AKfycbzb7MYnH34TTOfs6Uy9ZBg3KM32p4_1m2e6ggHV1ZtVhNwGRjpkhNeTlg-5Yxw9D9AWOA/exec"

-- ── 1. Detectar nombre del chat activo en WhatsApp ──────────────────────────
set nombreDetectado to ""
try
	tell application "System Events"
		tell process "WhatsApp"
			-- El título del panel lateral activo suele estar en un static text
			-- dentro del grupo de encabezado de la conversación
			set nombreDetectado to value of static text 1 of group 1 of group 1 of group 2 of splitter group 1 of window 1
		end tell
	end tell
end try

-- Si no se pudo detectar, intentar con el título de la ventana
if nombreDetectado is "" then
	try
		tell application "System Events"
			tell process "WhatsApp"
				set nombreDetectado to title of window 1
				if nombreDetectado is "WhatsApp" then set nombreDetectado to ""
			end tell
		end tell
	end try
end if

-- ── 2. Diálogo con datos del contacto ──────────────────────────────────────
set dialogResult to display dialog "Agregar contacto al CRM de Tizado" & return & return & ¬
	"Nombre:" & return & "(completá o corregí)" ¬
	default answer nombreDetectado ¬
	with title "CRM Tizado — Nuevo Contacto" ¬
	buttons {"Cancelar", "Continuar"} ¬
	default button "Continuar"

if button returned of dialogResult is "Cancelar" then return
set nombreFinal to text returned of dialogResult
if nombreFinal is "" then
	display alert "El nombre no puede estar vacío." as warning
	return
end if

set dialogTel to display dialog "Teléfono del contacto:" ¬
	default answer "" ¬
	with title "CRM Tizado — Nuevo Contacto" ¬
	buttons {"Cancelar", "Agregar"} ¬
	default button "Agregar"

if button returned of dialogTel is "Cancelar" then return
set telefonoFinal to text returned of dialogTel

set dialogNota to display dialog "Nota opcional (ej: interesado en casa en Bella Vista):" ¬
	default answer "" ¬
	with title "CRM Tizado — Nuevo Contacto" ¬
	buttons {"Cancelar", "Agregar al CRM"} ¬
	default button "Agregar al CRM"

if button returned of dialogNota is "Cancelar" then return
set notaFinal to text returned of dialogNota

-- ── 3. Construir timestamp ──────────────────────────────────────────────────
set ahora to do shell script "date -u +\"%Y-%m-%dT%H:%M:%SZ\""
set fechaHoy to do shell script "date +\"%Y-%m-%d\""

-- ── 4. Escapar comillas para JSON ───────────────────────────────────────────
set nombreJSON to do shell script "echo " & quoted form of nombreFinal & " | sed 's/\"/\\\\\"/g'"
set telefonoJSON to do shell script "echo " & quoted form of telefonoFinal & " | sed 's/\"/\\\\\"/g'"
set notaJSON to do shell script "echo " & quoted form of notaFinal & " | sed 's/\"/\\\\\"/g'"

-- ── 5. POST al Apps Script ──────────────────────────────────────────────────
set jsonPayload to "{\"action\":\"addContact\",\"contact\":{\"nombre\":\"" & nombreJSON & "\",\"telefono\":\"" & telefonoJSON & "\",\"origen\":\"WhatsApp\",\"estado\":\"Nuevo\",\"createdAt\":\"" & ahora & "\",\"notas\":[{\"date\":\"" & fechaHoy & "\",\"time\":\"\",\"text\":\"" & notaJSON & "\"}]}}"

set curlCmd to "curl -s -L -X POST " & quoted form of SHEETS_URL & ¬
	" -H 'Content-Type: application/json'" & ¬
	" -d " & quoted form of jsonPayload

set respuesta to do shell script curlCmd

-- ── 6. Confirmar ────────────────────────────────────────────────────────────
if respuesta contains "\"ok\":true" or respuesta contains "ok" then
	display notification "Contacto \"" & nombreFinal & "\" agregado al CRM." ¬
		with title "CRM Tizado" ¬
		subtitle "✓ Sincronizado con Google Sheets"
else
	display alert "El contacto se procesó pero la respuesta fue inesperada." & return & return & respuesta as warning
end if
