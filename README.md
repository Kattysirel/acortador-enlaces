# Acortador de enlaces (S3 + EC2 + DynamoDB)

- `frontend/` → HTML/CSS/JS, publicado en S3 (sitio estático)
- `backend/` → FastAPI + Boto3, corre en EC2 con systemd
- DynamoDB tabla `short_links` (clave `short_code`, UUID generado en el backend)
- `deploy/` → archivos de configuración usados en los comandos de abajo

Endpoints: `POST /shorten`, `GET /{short_code}` (307), `GET /urls/{short_code}`.

# Guía de despliegue (todo en PowerShell, región us-east-1)

## 0. Preparar AWS CLI

1. Instalar: `winget install Amazon.AWSCLI` y **cerrar y abrir** PowerShell.
2. Consola AWS → IAM → Users → Create user → permisos `AdministratorAccess` → Security credentials → Create access key (CLI).
3. Configurar:

```powershell
aws configure
# Access Key ID, Secret, region: us-east-1, output: json
aws sts get-caller-identity
```

Variables que usaremos (ejecutar en la carpeta del repo):

```powershell
$REGION = "us-east-1"
$ACCOUNT_ID = aws sts get-caller-identity --query Account --output text
$BUCKET = "acortador-$ACCOUNT_ID"
```

## 1. DynamoDB

```powershell
aws dynamodb create-table --table-name short_links --attribute-definitions AttributeName=short_code,AttributeType=S --key-schema AttributeName=short_code,KeyType=HASH --billing-mode PAY_PER_REQUEST --region $REGION
aws dynamodb wait table-exists --table-name short_links --region $REGION
```

## 2. Bucket S3 (frontend)

```powershell
aws s3api create-bucket --bucket $BUCKET --region $REGION
aws s3api put-public-access-block --bucket $BUCKET --public-access-block-configuration BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false
(Get-Content deploy/bucket-policy.json) -replace 'BUCKET_NAME',$BUCKET | Set-Content -Encoding ascii deploy/bucket-policy.generated.json
aws s3api put-bucket-policy --bucket $BUCKET --policy file://deploy/bucket-policy.generated.json
aws s3 website s3://$BUCKET --index-document index.html
```

URL del frontend (la usaremos como CORS):

```powershell
$ORIGIN = "http://$BUCKET.s3-website-us-east-1.amazonaws.com"
$ORIGIN
```

## 3. Rol IAM para EC2

```powershell
aws iam create-role --role-name acortador-role --assume-role-policy-document file://deploy/trust-policy.json
(Get-Content deploy/dynamodb-policy.json) -replace 'ACCOUNT_ID',$ACCOUNT_ID | Set-Content -Encoding ascii deploy/dynamodb-policy.generated.json
aws iam put-role-policy --role-name acortador-role --policy-name dynamodb-short-links --policy-document file://deploy/dynamodb-policy.generated.json
aws iam create-instance-profile --instance-profile-name acortador-profile
aws iam add-role-to-instance-profile --instance-profile-name acortador-profile --role-name acortador-role
Start-Sleep -Seconds 15
```

## 4. Key pair y Security Group

```powershell
aws ec2 create-key-pair --key-name acortador-key --query KeyMaterial --output text --region $REGION | Out-File -Encoding ascii acortador-key.pem
icacls acortador-key.pem /inheritance:r
icacls acortador-key.pem /grant:r "$($env:USERNAME):(R)"

$VPC = aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query "Vpcs[0].VpcId" --output text --region $REGION
$SG = aws ec2 create-security-group --group-name acortador-sg --description "Acortador" --vpc-id $VPC --query GroupId --output text --region $REGION
$MYIP = (Invoke-RestMethod https://checkip.amazonaws.com).Trim()
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 22 --cidr "$MYIP/32" --region $REGION
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 8000 --cidr 0.0.0.0/0 --region $REGION
```

## 5. Lanzar la EC2

```powershell
$AMI = aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text --region $REGION
$IID = aws ec2 run-instances --image-id $AMI --instance-type t3.micro --key-name acortador-key --security-group-ids $SG --iam-instance-profile Name=acortador-profile --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=acortador}]" --query "Instances[0].InstanceId" --output text --region $REGION
aws ec2 wait instance-running --instance-ids $IID --region $REGION

# IP fija para que no cambie
$ALLOC = aws ec2 allocate-address --domain vpc --query AllocationId --output text --region $REGION
aws ec2 associate-address --instance-id $IID --allocation-id $ALLOC --region $REGION
$IP = aws ec2 describe-addresses --allocation-ids $ALLOC --query "Addresses[0].PublicIp" --output text --region $REGION
$IP
```

## 6. Configurar el backend por SSH

```powershell
ssh -i acortador-key.pem ec2-user@$IP
```

(Responder `yes` la primera vez.) Ya dentro de la EC2 (Linux):

```bash
sudo dnf install -y git python3.11
git clone https://github.com/Kattysirel/acortador-enlaces.git
cd acortador-enlaces/backend
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env
```

En `.env` pon (con tus valores reales de `$IP` y `$ORIGIN`, sin espacios ni barra final):

```
TABLE_NAME=short_links
AWS_REGION=us-east-1
PUBLIC_BASE_URL=http://TU_IP:8000
ALLOWED_ORIGIN=http://acortador-TU_ACCOUNT_ID.s3-website-us-east-1.amazonaws.com
```

Guardar: `Ctrl+O`, Enter, `Ctrl+X`. Luego:

```bash
sudo cp ../deploy/acortador.service /etc/systemd/system/acortador.service
sudo systemctl daemon-reload
sudo systemctl enable --now acortador
sudo systemctl status acortador
exit
```

Probar desde Windows:

```powershell
curl.exe -I http://${IP}:8000/docs
```

Debe responder `200 OK`.

## 7. Subir el frontend

Poner la IP en `frontend/app.js`:

```powershell
(Get-Content frontend/app.js) -replace 'IP_PUBLICA_EC2',$IP | Set-Content -Encoding utf8 frontend/app.js
aws s3 sync frontend s3://$BUCKET --delete
$ORIGIN
```

Abrir `$ORIGIN` en el navegador (con **http**, no https).

## 8. Pruebas

```powershell
# crear
curl.exe -X POST http://${IP}:8000/shorten -H "Content-Type: application/json" -d '{\"original_url\":\"https://www.example.com\"}'
# copia el short_code de la respuesta:
$CODE = "PEGA_AQUI_EL_UUID"
curl.exe -i http://${IP}:8000/$CODE          # 307 + Location
curl.exe http://${IP}:8000/urls/$CODE        # JSON
curl.exe -i http://${IP}:8000/00000000-0000-0000-0000-000000000000   # 404
aws dynamodb scan --table-name short_links --region $REGION          # ver registros

# reinicio del backend
ssh -i acortador-key.pem ec2-user@$IP "sudo systemctl restart acortador"
curl.exe -i http://${IP}:8000/$CODE          # sigue funcionando
```

## 9. Limpieza (después de entregar)

```powershell
aws ec2 terminate-instances --instance-ids $IID --region $REGION
aws ec2 wait instance-terminated --instance-ids $IID --region $REGION
aws ec2 release-address --allocation-id $ALLOC --region $REGION
aws s3 rb s3://$BUCKET --force
aws dynamodb delete-table --table-name short_links --region $REGION
```
