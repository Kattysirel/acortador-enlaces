# Acortador de enlaces (S3 + EC2 + DynamoDB)

- `frontend/` → HTML/CSS/JS, publicado en S3 (sitio estático)
- `backend/` → FastAPI + Boto3, corre en EC2 con systemd
- DynamoDB tabla `short_links` (clave `short_code`, UUID generado en el backend)
- `deploy/` → servicio systemd y políticas JSON

Endpoints: `POST /shorten`, `GET /{short_code}` (307), `GET /urls/{short_code}`.

# Guía de despliegue (consola web de AWS en español)

Entra a https://console.aws.amazon.com y, arriba a la derecha, selecciona la región **US East (N. Virginia) us-east-1**. No la cambies en todo el proceso.

Valores que se usan en toda la guía (ya puestos para esta cuenta):

| Dato | Valor |
|------|-------|
| ID de cuenta | `614315078836` |
| Tabla DynamoDB | `short_links` |
| Bucket S3 | `acortador-614315078836` |
| Rol IAM | `acortador-role` |
| Endpoint del sitio S3 (origen) | `http://acortador-614315078836.s3-website-us-east-1.amazonaws.com` |

> Los nombres de los botones pueden variar un poco según la versión de la consola; si no ves uno exacto, busca el más parecido.

## 1. DynamoDB

1. Busca **DynamoDB** → **Tablas** → **Crear tabla**.
2. Nombre de la tabla: `short_links`
3. Clave de partición: `short_code`, tipo **Cadena**.
4. Configuración de la tabla: **Configuración predeterminada** → **Crear tabla**.

## 2. Bucket S3 (frontend)

1. Busca **S3** → **Crear bucket**.
2. Nombre del bucket: `acortador-614315078836`. Región us-east-1.
3. En **Configuración de bloqueo de acceso público de este bucket**: **desmarca** "Bloquear todo el acceso público" y marca el aviso de que entiendes los riesgos.
4. **Crear bucket**.
5. Entra al bucket → pestaña **Permisos** → **Política de bucket** → **Editar**, borra lo que haya y pega esto **tal cual**:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::acortador-614315078836/*"
  }]
}
```

Luego **Guardar cambios**.

6. Pestaña **Propiedades** → baja hasta **Alojamiento de sitios web estáticos** → **Editar** → **Habilitar** → Documento de índice: `index.html` → **Guardar cambios**.
7. En esa misma sección aparece el **Punto de conexión del sitio web del bucket**. Debe ser:
   `http://acortador-614315078836.s3-website-us-east-1.amazonaws.com`
   Es el origen que se pone en CORS.

## 3. Rol IAM para la EC2

1. Busca **IAM** → **Roles** → **Crear rol**.
2. Tipo de entidad de confianza: **Servicio de AWS** → Caso de uso: **EC2** → **Siguiente**.
3. No selecciones ninguna política → **Siguiente**.
4. Nombre del rol: `acortador-role` → **Crear rol**.
5. Entra al rol `acortador-role` → **Agregar permisos** → **Crear política insertada** → pestaña **JSON**, borra lo que haya y pega **tal cual**:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["dynamodb:GetItem", "dynamodb:PutItem"],
    "Resource": "arn:aws:dynamodb:us-east-1:614315078836:table/short_links"
  }]
}
```

6. **Siguiente** → Nombre de la política: `dynamodb-short-links` → **Crear política**.

## 4. Lanzar la EC2

1. Busca **EC2** → **Lanzar instancia**.
2. Nombre: `acortador`.
3. AMI: **Amazon Linux 2023** (la primera, "Apto para la capa gratuita").
4. Tipo de instancia: `t3.micro` (o `t2.micro` si es la que dice capa gratuita).
5. Par de claves: **Continuar sin un par de claves** (nos conectaremos desde el navegador).
6. **Configuración de red** → **Editar**:
   - Marca **Crear grupo de seguridad**, nombre `acortador-sg`.
   - Regla 1 (SSH): Tipo `SSH`, Tipo de origen **Personalizada**, valor `18.206.107.24/29` (rango de EC2 Instance Connect de us-east-1; así el SSH queda restringido y puedes entrar desde el navegador).
   - **Agregar regla de grupo de seguridad**: Tipo **TCP personalizado**, Intervalo de puertos `8000`, Origen **En cualquier lugar (0.0.0.0/0)**.
7. **Detalles avanzados** → **Perfil de instancia de IAM**: elige `acortador-role`.
8. **Lanzar instancia**.

### IP fija (para que no cambie)

1. En EC2, menú izquierdo → **Direcciones IP elásticas** → **Asignar dirección IP elástica** → **Asignar**.
2. Selecciónala → **Acciones** → **Asociar dirección IP elástica** → Instancia: `acortador` → **Asociar**.
3. **Copia esa IP**: es tu `IP_EC2`.

## 5. Configurar el backend

1. EC2 → **Instancias** → selecciona `acortador` → **Conectar** → pestaña **EC2 Instance Connect** → **Conectar**. Se abre una terminal en el navegador.
2. Pega esto (línea por línea o todo junto):

```bash
sudo dnf install -y git python3.11 python3.11-pip
git clone https://github.com/Kattysirel/acortador-enlaces.git
cd acortador-enlaces/backend
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env
```

3. En `nano` deja el archivo así, cambiando **solo** `IP_EC2` por tu Elastic IP (sin barra final):

```
TABLE_NAME=short_links
AWS_REGION=us-east-1
PUBLIC_BASE_URL=http://IP_EC2:8000
ALLOWED_ORIGIN=http://acortador-614315078836.s3-website-us-east-1.amazonaws.com
```

Guardar: `Ctrl+O`, Enter, `Ctrl+X`.

4. Activar el servicio:

```bash
sudo cp ../deploy/acortador.service /etc/systemd/system/acortador.service
sudo systemctl daemon-reload
sudo systemctl enable --now acortador
sudo systemctl status acortador
```

Debe decir `active (running)` (sal con `q`).

5. Prueba en el navegador: `http://IP_EC2:8000/docs` → debe abrir la documentación de la API.

## 6. Subir el frontend

1. En VSCode abre `frontend/app.js` y cambia la primera línea:
   `const API_URL = "http://IP_EC2:8000";` (tu IP real, sin barra final). Guarda.
2. En la consola de S3 entra a tu bucket → **Cargar** → **Agregar archivos** → selecciona `index.html`, `style.css` y `app.js` de la carpeta `frontend` → **Cargar**.
3. Abre el punto de conexión del sitio web del paso 2.7 (con **http**, no https).

(Opcional: haz commit y push de tu `app.js` modificado a GitHub.)

## 7. Pruebas (para el video)

1. Abre la página de S3, pega una URL (ej. `https://www.wikipedia.org`) y pulsa **Acortar**.
2. Copia el enlace corto y ábrelo en otra pestaña → te redirige a la URL original.
3. Cambia el UUID por otro inventado → muestra `Enlace no encontrado` (404).
4. Abre `http://IP_EC2:8000/urls/TU_UUID` → muestra el JSON del enlace.
5. DynamoDB → **Tablas** → `short_links` → **Explorar elementos de la tabla** → se ven los registros.
6. Reinicio: en la terminal de EC2 Instance Connect ejecuta `sudo systemctl restart acortador` y vuelve a abrir el enlace corto: sigue funcionando.

## 8. Limpieza (solo después de que te califiquen)

- EC2: terminar la instancia, y en Direcciones IP elásticas: **Liberar**.
- S3: vaciar y eliminar el bucket.
- DynamoDB: eliminar la tabla.
- IAM: eliminar el rol `acortador-role`.
