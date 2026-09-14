# Manual de usuario — ServiceMesh

> Guía paso a paso para instalar, desplegar y probar el proyecto desde cero. Documento vivo:
> se amplía a medida que se cierran nuevas fases (circuit breaker, Kiali, etc.).

## 1. ¿Qué es este proyecto?

Tres microservicios FastAPI (`usuarios`, `productos`, `pedidos`) corriendo en Kubernetes
(Minikube), con Istio añadiendo encriptación automática (mTLS), enrutamiento de tráfico,
despliegues canary y resiliencia — todo sin tocar el código de la aplicación.

## 2. Requisitos previos

- Windows 10/11 con **Docker Desktop** (backend WSL2), con al menos 10GB de RAM asignados a
  WSL2 (ver `.wslconfig` más abajo).
- `kubectl`, `minikube`, `git` instalados.
- `istioctl` 1.20.0 (se instala en el paso 4).
- Al menos 16GB de RAM física en la máquina (recomendado).

## 3. Configurar memoria de Docker Desktop (WSL2)

Si Docker Desktop usa el backend WSL2, la memoria no se configura desde su interfaz gráfica.
Crea o edita `%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
memory=10GB
processors=4
```

Luego, en una terminal:
```powershell
wsl --shutdown
```
Y vuelve a abrir Docker Desktop.

## 4. Crear el cluster e instalar Istio

```powershell
# Cluster de Minikube con recursos suficientes para Istio
minikube start --cpus=4 --memory=8192 --driver=docker

# Descargar istioctl para Windows (el script oficial curl|sh NO funciona en PowerShell)
curl.exe -L -o istio-1.20.0-win.zip https://github.com/istio/istio/releases/download/1.20.0/istio-1.20.0-win.zip
Expand-Archive -Path istio-1.20.0-win.zip -DestinationPath . -Force
$env:PATH += ";$PWD\istio-1.20.0\bin"
istioctl version --remote=false

# Instalar Istio (perfil demo: control plane + gateways, SIN los addons de observabilidad)
istioctl install --set profile=demo -y

# Instalar los addons de observabilidad (Prometheus, Grafana, Jaeger, Kiali) por separado
kubectl apply -f istio-1.20.0/samples/addons
kubectl get pods -n istio-system
```

> Nota: el `$env:PATH` de arriba solo dura la sesión actual de PowerShell. Si abres una
> terminal nueva, repite esa línea (o agrega la carpeta al PATH de Windows de forma
> permanente).

## 5. Construir y desplegar los tres servicios

```powershell
# Apunta el cliente Docker al daemon INTERNO de minikube (no al de Windows)
minikube docker-env | Invoke-Expression

# Construye las 3 imágenes
docker build -t usuarios-service:v1 .\usuarios-service
docker build -t productos-service:v1 .\productos-service
docker build -t pedidos-service:v1 .\pedidos-service

# Despliega el namespace y los 3 servicios
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/usuarios-deployment.yaml
kubectl apply -f k8s/productos-deployment.yaml
kubectl apply -f k8s/pedidos-deployment.yaml

# Verifica que cada Pod tenga 2/2 (app + sidecar de Istio)
kubectl get pods -n servicemesh
```

## 6. Probar que el sistema funciona (end-to-end)

```powershell
kubectl run test-curl --image=curlimages/curl -n servicemesh --restart=Never -- sleep 3600
kubectl wait --for=condition=Ready pod/test-curl -n servicemesh --timeout=30s

kubectl exec -n servicemesh test-curl -- curl -s http://usuarios-service/users
kubectl exec -n servicemesh test-curl -- curl -s http://productos-service/products
kubectl exec -n servicemesh test-curl -- curl -s -X POST "http://pedidos-service/orders?user_id=1&product_id=1"

kubectl delete pod test-curl -n servicemesh
```
El último comando debe devolver un JSON con `order_id`, `user`, `product` y `status: created`.

## 7. Activar mTLS estricto

```powershell
kubectl apply -f k8s/mtls-strict.yaml
```
Verificación (un pod sin sidecar, fuera del mesh, debe ser rechazado):
```powershell
kubectl run test-plano --image=curlimages/curl --restart=Never -n default -- curl -s -m 5 http://usuarios-service.servicemesh.svc.cluster.local/users
kubectl logs test-plano -n default   # debe fallar / no responder
kubectl delete pod test-plano -n default
```

## 8. Traffic routing (DestinationRule + VirtualService)

```powershell
kubectl apply -f k8s/usuarios-destination-rule.yaml
kubectl apply -f k8s/usuarios-virtual-service.yaml
kubectl get destinationrule,virtualservice -n servicemesh
```

## 9. Canary deployment (90% v1 / 10% v2)

```powershell
# Construye e instala la versión 2 de usuarios-service
minikube docker-env | Invoke-Expression
docker build -t usuarios-service:v2 .\usuarios-service-v2
kubectl apply -f k8s/usuarios-v2-deployment.yaml
kubectl get pods -n servicemesh -l app=usuarios   # deben verse v1 y v2, todos 2/2 Running

# El VirtualService (k8s/usuarios-virtual-service.yaml) ya está configurado 90/10 —
# si necesitas volver a aplicarlo tras editarlo:
kubectl apply -f k8s/usuarios-virtual-service.yaml
```

Para comprobar el split de tráfico real, dispara varias decenas de requests y cuenta cuántas
trae el campo `"served_by":"v2"`:
```powershell
kubectl run test-canary --image=curlimages/curl -n servicemesh --restart=Never -- sleep 3600
kubectl wait --for=condition=Ready pod/test-canary -n servicemesh --timeout=30s

Remove-Item canary_check.txt -ErrorAction SilentlyContinue
for ($i=1; $i -le 50; $i++) { kubectl exec -n servicemesh test-canary -- curl -s -X POST "http://pedidos-service/orders?user_id=1&product_id=1" | Out-File -Append -Encoding utf8 canary_check.txt }
(Select-String -Path canary_check.txt -Pattern "served_by").Count   # debería rondar el 10% del total

kubectl delete pod test-canary -n servicemesh
Remove-Item canary_check.txt
```

## 10. Solución de problemas comunes

| Síntoma | Causa | Solución |
|---|---|---|
| `sh` no reconocido en PowerShell | El script `downloadIstio` es para Bash/Linux/macOS | Descargar el `.zip` de Windows directamente (paso 4) |
| `ImagePullBackOff` en un Deployment | La imagen se construyó en el Docker Desktop de Windows, no en el daemon interno de minikube | Correr `minikube docker-env \| Invoke-Expression` **antes** de cada `docker build`, y reconstruir |
| `istioctl authn tls-check` no existe | Comando removido en Istio ≥1.9 | Usar `istioctl x describe pod <pod>.<namespace>` |
| `kubectl exec -c istio-proxy -- curl ...` falla ("not found") | La imagen `proxyv2` no incluye `curl` | Usar `pilot-agent request GET stats` en su lugar |
| Un `VirtualService`/`DestinationRule` editado no cambia el comportamiento | Se editó el archivo local pero no se volvió a correr `kubectl apply` | Siempre confirmar con `kubectl get <recurso> -o yaml` que el cluster refleja el archivo local |
| El canary "no reparte tráfico" pero toda la config se ve bien | Puede que la imagen desplegada no sea la que se cree (build desde la carpeta equivocada, cache viejo, etc.) | `kubectl exec ... -- cat <archivo>` dentro del Pod real para confirmar el código desplegado |

## 11. Pendiente (próximas fases)

- **Circuit breaker** (`outlierDetection` en `productos-destination-rule.yaml`) — requiere
  instalar `hey` como generador de carga.
- **Kiali dashboard** — visualización del grafo de tráfico del mesh.
