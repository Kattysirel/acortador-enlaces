# Acortador de enlaces (S3 + EC2 + DynamoDB)

- `frontend/` → HTML/CSS/JS, publicado en S3 (sitio estático)
- `backend/` → FastAPI + Boto3, corre en EC2 con systemd
- DynamoDB tabla `short_links` (clave `short_code`, UUID generado en el backend)
- `deploy/` → servicio systemd y políticas JSON

Endpoints: `POST /shorten`, `GET /{short_code}` (307), `GET /urls/{short_code}`.

# Guía de despliegue (todo desde la consola web de AWS)

Entra a https://console.aws.amazon.com y, arriba a la derecha, selecciona la región **US East (N. Virginia) us-east-1**. No la cambies en todo el proceso.

Anota tu **Account ID** (arriba a la derecha, clic en tu nombre → número de 12 dígitos). Lo llamaremos `ACCOUNT_ID`.

## 1. DynamoDB

1. Busca **DynamoDB** → **Tables** → **Create table**.
2. Table name: `short_links`
3. Partition key: `short_code`, tipo **String**.
4. Table settings: **Default settings** → **Create table**.

## 2. Bucket S3 (frontend)

1. Busca **S3** → **Create bucket**.
2. Bucket name: `acortador-ACCOUNT_ID` (ej: `acortador-123456789012`). Región us-east-1.
3. En **Block Public Access settings**: **desmarca** "Block all public access" y marca el aviso de que entiendes.
4. **Create bucket**.
5. Entra al bucket → pestaña **Permissions** → **Bucket policy** → **Edit** y pega esto (cambia `TU_BUCKET`):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::TU_BUCKET/*"
  }]
}
```

6. Pestaña **Properties** → baja hasta **Static website hosting** → **Edit** → **Enable** → Index document: `index.html` → **Save changes**.
7. En esa misma sección aparece la **Bucket website endpoint** (`http://acortador-....s3-website-us-east-1.amazonaws.com`). **Cópiala**: es tu `ORIGEN` (para CORS).

## 3. Rol IAM para la EC2

1. Busca **IAM** → **Roles** → **Create role**.
2. Trusted entity: **AWS service** → Use case: **EC2** → **Next**.
3. No selecciones ninguna política → **Next**.
4. Role name: `acortador-role` → **Create role**.
5. Entra al rol `acortador-role` → **Add permissions** → **Create inline policy** → pestaña **JSON** y pega (cambia `ACCOUNT_ID`):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["dynamodb:GetItem", "dynamodb:PutItem"],
    "Resource": "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/short_links"
  }]
}
```

6. **Next** → Policy name: `dynamodb-short-links` → **Create policy**.

## 4. Lanzar la EC2

1. Busca **EC2** → **Launch instance**.
2. Name: `acortador`.
3. AMI: **Amazon Linux 2023** (la primera, "Free tier eligible").
4. Instance type: `t3.micro` (o `t2.micro` si es la que dice free tier).
5. Key pair: **Proceed without a key pair** (nos conectaremos desde el navegador).
6. **Network settings** → **Edit**:
   - Marca **Create security group**, nombre `acortador-sg`.
   - Regla 1 (SSH): Type `SSH`, Source type **Custom**, valor `18.206.107.24/29` (rango de EC2 Instance Connect de us-east-1; así el SSH queda restringido y puedes entrar desde el navegador).
   - **Add security group rule**: Type **Custom TCP**, Port range `8000`, Source **Anywhere (0.0.0.0/0)**.
7. **Advanced details** → **IAM instance profile**: elige `acortador-role`.
8. **Launch instance**.

### IP fija (para que no cambie)

1. En EC2, menú izquierdo → **Elastic IPs** → **Allocate Elastic IP address** → **Allocate**.
2. Selecciónala → **Actions** → **Associate Elastic IP address** → Instance: `acortador` → **Associate**.
3. **Copia esa IP**: es tu `IP_EC2`.

## 5. Configurar el backend

1. EC2 → **Instances** → selecciona `acortador` → **Connect** → pestaña **EC2 Instance Connect** → **Connect**. Se abre una terminal en el navegador.
2. Pega esto (línea por línea o todo junto):

```bash
sudo dnf install -y git python3.11
git clone https://github.com/Kattysirel/acortador-enlaces.git
cd acortador-enlaces/backend
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env
```

3. En `nano` deja el archivo así (con tu IP y tu ORIGEN, sin barra final):

```
TABLE_NAME=short_links
AWS_REGION=us-east-1
PUBLIC_BASE_URL=http://IP_EC2:8000
ALLOWED_ORIGIN=http://acortador-ACCOUNT_ID.s3-website-us-east-1.amazonaws.com
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
2. En la consola de S3 entra a tu bucket → **Upload** → **Add files** → selecciona `index.html`, `style.css` y `app.js` de la carpeta `frontend` → **Upload**.
3. Abre la Bucket website endpoint del paso 2.7 (con **http**, no https).

(Opcional: haz commit y push de tu `app.js` modificado a GitHub.)

## 7. Pruebas (para el video)

1. Abre la página de S3, pega una URL (ej. `https://www.wikipedia.org`) y pulsa **Acortar**.
2. Copia el enlace corto y ábrelo en otra pestaña → te redirige a la URL original.
3. Cambia el UUID por otro inventado → muestra `Enlace no encontrado` (404).
4. Abre `http://IP_EC2:8000/urls/TU_UUID` → muestra el JSON del enlace.
5. DynamoDB → **Tables** → `short_links` → **Explore table items** → se ven los registros.
6. Reinicio: en la terminal de EC2 Instance Connect ejecuta `sudo systemctl restart acortador` y vuelve a abrir el enlace corto: sigue funcionando.

## 8. Limpieza (solo después de que te califiquen)

- EC2: terminar la instancia, y en Elastic IPs: **Release**.
- S3: vaciar y eliminar el bucket.
- DynamoDB: eliminar la tabla.
- IAM: eliminar el rol `acortador-role`.
