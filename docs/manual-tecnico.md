# Manual técnico — ServiceMesh

> Documento vivo. Se actualiza al cerrar cada fase de la guía (`guia-servicemesh-istio-k8s.html`),
> registrando arquitectura, decisiones técnicas e incidentes reales encontrados durante el
> desarrollo. Es el historial "de verdad" del proyecto — a diferencia del `README.md` (que
> resume el estado actual), este documento conserva el contexto completo de por qué las cosas
> quedaron como quedaron, incluyendo los errores que se cometieron y cómo se diagnosticaron.

## 1. Resumen del proyecto

ServiceMesh es un proyecto de práctica de Kubernetes + Istio: tres microservicios FastAPI
(`usuarios`, `productos`, `pedidos`) desplegados en Minikube, sobre los cuales Istio añade
mTLS automático, traffic routing, canary deployments, circuit breaking y observabilidad —
sin modificar una sola línea del código de la aplicación. Es el tercer proyecto de una serie
de práctica de Kubernetes (después de PulseBoard y FlowPipe).

## 2. Arquitectura

```
                    ┌─────────────────────────────────────┐
                    │        namespace: servicemesh        │
                    │        (istio-injection: enabled)    │
                    │                                       │
  cliente/test ───▶ │  pedidos-service ──▶ usuarios-service │
                    │        │                (v1 + v2)     │
                    │        └──────────▶ productos-service │
                    │                                       │
                    │  Cada Pod: [app container] + [Envoy]  │
                    └─────────────────────────────────────┘
                              ▲
                              │ control plane (xDS)
                        istiod (namespace istio-system)
```

- **`usuarios-service`**: CRUD en memoria de usuarios. Tiene dos versiones desplegadas en
  paralelo (`v1`, `v2`) para demostrar canary deployment.
- **`productos-service`**: CRUD en memoria de productos.
- **`pedidos-service`**: orquesta una llamada a `usuarios-service` y a `productos-service`
  para crear una "orden" — es el único servicio que hace llamadas salientes a otros servicios
  del mesh, por lo que es el mejor punto para observar el comportamiento del traffic routing.
- Cada Pod, al estar en un namespace con `istio-injection: enabled`, recibe automáticamente
  un segundo contenedor (`istio-proxy`, Envoy) inyectado por el webhook de Istio. Todo el
  tráfico de red del Pod pasa a través de este proxy (vía reglas de `iptables`), de forma
  transparente para la aplicación.

## 3. Stack técnico

| Capa | Tecnología / versión |
|---|---|
| Apps | Python 3.11, FastAPI 0.109.0, Uvicorn 0.27.0, httpx 0.26.0 (solo `pedidos-service`) |
| Contenedores | Docker Desktop (backend WSL2) |
| Cluster | Minikube v1.38.1, driver Docker, `--cpus=4 --memory=8192` |
| Kubernetes | v1.35.1 (control plane del cluster minikube) |
| Service mesh | Istio 1.20.0 (`istioctl`), perfil `demo` |
| Observabilidad | Kiali, Grafana, Jaeger, Prometheus (instalados vía `samples/addons/` del release de Istio) |
| Control de versiones | Git, modelo GitFlow (`main`/`develop` + `feature/<fase>`) |

## 4. Estructura del repositorio

```
usuarios-service/        # v1 de usuarios-service (main.py, requirements.txt, Dockerfile)
usuarios-service-v2/     # v2 de usuarios-service, para el canary deployment
productos-service/
pedidos-service/
k8s/
  namespace.yaml                    # namespace servicemesh + istio-injection: enabled
  usuarios-deployment.yaml          # Deployment + Service de usuarios v1
  usuarios-v2-deployment.yaml       # Deployment de usuarios v2 (sin Service propio)
  productos-deployment.yaml
  pedidos-deployment.yaml
  mtls-strict.yaml                  # PeerAuthentication (Fase 3)
  usuarios-destination-rule.yaml    # DestinationRule con subsets v1/v2 (Fase 4)
  usuarios-virtual-service.yaml     # VirtualService con pesos y retries (Fase 4/5)
docs/
  manual-tecnico.md                 # este documento
  manual-usuario.md                 # guía de instalación y uso paso a paso
```

`ClaudeInstructionsGeneral.md` y `guia-servicemesh-istio-k8s.html` son archivos de referencia
puramente locales (no se suben al repositorio).

## 5. Historial de fases

### Fase 0 — Preparación del entorno
- Docker Desktop, con backend **WSL2**: la memoria/CPU no se configura desde la UI de Docker
  Desktop (esos sliders desaparecen en modo WSL2), sino desde `%USERPROFILE%\.wslconfig`.
  Se configuró `memory=10GB`, `processors=4`.
- Cluster: `minikube start --cpus=4 --memory=8192 --driver=docker`.
- `istioctl` 1.20.0: en Windows, el script oficial `curl -L https://istio.io/downloadIstio | sh`
  **no funciona** (requiere `sh`, y aunque se tuviera, el script no reconoce Windows como SO
  soportado — solo detecta `Darwin` o asume `Linux`). Se descargó directamente el release
  `.zip` para Windows desde GitHub y se extrajo con `Expand-Archive`.
- `istioctl install --set profile=demo -y` — el perfil `demo` **no** instala Kiali/Grafana/Jaeger
  automáticamente (a diferencia de lo que sugieren algunas guías); esos addons son manifiestos
  YAML separados en `istio-1.20.0/samples/addons/`, que se aplican con
  `kubectl apply -f istio-1.20.0/samples/addons`.

### Fase servicios-base — Los 3 microservicios en Kubernetes
- Los tres servicios FastAPI, construidos como imágenes Docker y desplegados como
  `Deployment` (2 réplicas) + `Service` en el namespace `servicemesh`.
- Detalle clave del `Deployment`: cada Pod lleva la label `version: v1` desde el inicio,
  aunque en ese momento solo existe una versión — se necesita más adelante para que
  `DestinationRule` pueda definir subsets por versión sin tener que re-etiquetar nada.
- Verificación real (no solo "los Pods existen"): un Pod de prueba (`curlimages/curl`) dentro
  del mismo namespace, llamando a `POST /orders` en `pedidos-service`, confirmando la cadena
  completa `pedidos → usuarios + productos`.

### Fase mTLS — PeerAuthentication STRICT
- `k8s/mtls-strict.yaml`: `PeerAuthentication` llamado `default` en el namespace `servicemesh`
  fuerza mTLS estricto para todos los workloads del namespace.
- Verificación de comportamiento real (no solo que el recurso se creó): un Pod **sin** sidecar,
  en el namespace `default` (sin `istio-injection`), intentando `curl` en HTTP plano contra
  `usuarios-service` — resultado esperado y confirmado: `Recv failure: Connection reset by peer`.
- Nota de herramienta: `istioctl authn tls-check` fue **removido** en versiones recientes de
  Istio. El reemplazo es `istioctl x describe pod <pod>.<namespace>` (sin `-n`, el namespace va
  pegado al nombre del pod con un punto).

### Fase traffic-routing — DestinationRule + VirtualService
- `usuarios-destination-rule.yaml`: define subsets `v1` y `v2` por label `version` (el subset
  `v2` se declara **antes** de que exista ningún Pod con esa versión — es válido, simplemente
  queda con 0 endpoints hasta que se despliegue).
- `usuarios-virtual-service.yaml`: enruta 100% a `v1`, con `timeout: 5s` y `retries` (3 intentos,
  2s por intento, en `5xx,reset,connect-failure`) — resiliencia añadida sin tocar el código
  Python de ningún servicio.

### Fase canary — Traffic splitting 90/10
- Se agregó `usuarios-service-v2/` (código con un campo extra `served_by: "v2"` y un usuario
  adicional, para poder distinguir visualmente qué versión responde) y
  `k8s/usuarios-v2-deployment.yaml`.
- El `VirtualService` se actualizó a dos destinos con pesos `90`/`10`.
- Ver la sección de incidentes (§7) para el detalle completo de la investigación de por qué
  el canary parecía no funcionar, y qué era en realidad.

## 6. Incidentes y su resolución (postmortems)

### 6.1 — Memoria insuficiente en Docker Desktop / WSL2
**Síntoma:** `minikube start --memory=8192` fallaba porque Docker Desktop solo tenía 7828MB
asignados.
**Causa:** con Docker Desktop en modo WSL2, la memoria de la VM se controla por
`%USERPROFILE%\.wslconfig` (sección `[wsl2]`), no por el slider de Settings → Resources de la
UI (que directamente desaparece en este modo).
**Solución:** crear `.wslconfig` con `memory=10GB` + `processors=4`, `wsl --shutdown`, reabrir
Docker Desktop.

### 6.2 — Binario de 84MB commiteado por error (istioctl.exe)
**Síntoma:** al hacer `git push`, GitHub advirtió sobre un archivo de 83.94MB
(`istio-1.20.0/bin/istioctl.exe`) — el directorio completo de la distribución de Istio había
quedado trackeado en git a pesar de existir un `.gitignore` que debía excluirlo.
**Causa probable:** el orden real de comandos ejecutados no coincidió exactamente con el
orden sugerido (crear `.gitignore` → `git init` → `git add .`); es posible que `git add .` se
ejecutara antes de que el `.gitignore` tuviera esa regla, o el archivo se sobreescribiera
después sin las exclusiones (ver también el incidente §6.5, relacionado).
**Solución:** reescritura completa del historial con `git filter-repo --path istio-1.20.0
--invert-paths --force` (elimina la ruta de *todos* los commits de *todas* las ramas), seguida
de `git push --force-with-lease` a las ramas ya publicadas. Se hizo respaldando primero el
directorio `istio-1.20.0/` fuera del repo, porque `filter-repo` re-sincroniza el working
directory con el nuevo historial y puede borrar del disco archivos que dejan de existir en él.
**Lección:** verificar `git status` / tamaño del `.git` antes del primer push de un proyecto
que incluya binarios grandes descargados localmente.

### 6.3 — VirtualService con indentación YAML incorrecta
**Síntoma:** al añadir el segundo destino (`subset: v2`) al `VirtualService`, Kubernetes lo
habría rechazado (o interpretado mal) porque `host`/`subset` del segundo destino quedaron al
mismo nivel de indentación que `destination:` y `weight:`, en vez de anidados dentro de
`destination:`.
**Lección:** en YAML, dos espacios de diferencia cambian por completo la estructura del
documento — no es solo estilo.

### 6.4 — Canary deployment: "el split no funciona" (en realidad, sí funcionaba)
**Síntoma:** con el `VirtualService` en 90/10, decenas (y luego cientos) de requests de prueba
consecutivas se respondían siempre por `v1`, nunca por `v2`.
**Investigación (en orden, descartando capas de abajo hacia arriba):**
1. ¿Coincidencia estadística? Descartado — la probabilidad de 220+ fallos seguidos con un 10%
   real es cercana a cero.
2. `DestinationRule` / labels de los Pods v2 / `istioctl analyze`: todo correcto.
3. `istioctl proxy-status`: todos los proxies `SYNCED` con el control plane.
4. `istioctl proxy-config routes <pod> --name 80 -o json`: el `weightedClusters` con 90/10
   estaba correctamente cargado en Envoy.
5. `istioctl proxy-config endpoints ... --cluster outbound|80|v2|...`: los 2 endpoints de v2
   aparecían `HEALTHY`.
6. Estadísticas reales de tráfico en Envoy (`pilot-agent request GET stats`, filtrando
   `istio_requests_total`): **aquí se encontró la prueba decisiva** — v2 sí estaba recibiendo
   y respondiendo tráfico exitosamente (200 OK), en una proporción muy cercana al 10%
   configurado (en una prueba aislada de 100 requests, exactamente 90/10).
**Causa raíz real:** el enrutamiento de Istio funcionaba perfectamente. El problema era que
la imagen `usuarios-service:v2` realmente desplegada en el cluster contenía el **código de
v1** (sin el campo `served_by` ni el usuario `Charlie`) — confirmado con
`kubectl exec ... deploy/usuarios-v2 -- cat main.py`. Es decir: v2 respondía tráfico real,
pero con el contenido incorrecto, porque en algún momento (muy probablemente al resolver un
`ImagePullBackOff` anterior, causado por construir la imagen en el daemon Docker equivocado —
el de Windows en vez del interno de minikube) la imagen se reconstruyó desde la carpeta
`usuarios-service/` (v1) en vez de `usuarios-service-v2/`.
**Solución:** reconstrucción de la imagen con `docker build --no-cache` apuntando
explícitamente a `.\usuarios-service-v2`, seguida de `kubectl rollout restart`.
**Lección general (la más valiosa de esta fase):** cuando la configuración de infraestructura
se ve perfecta pero el comportamiento observado no coincide, hay que separar dos preguntas
distintas: *"¿está bien configurado el enrutamiento?"* (verificable con `istioctl
proxy-config`/`proxy-status`/métricas) vs. *"¿el artefacto desplegado es realmente el código
que creo que es?"* (verificable con `kubectl exec ... cat <archivo>` dentro del contenedor
real). La segunda pregunta debería hacerse mucho antes cuando la primera ya se confirmó — es
un diagnóstico simple que ahorra mucho tiempo.

### 6.5 — Comandos de Windows/PowerShell que no son intercambiables con Linux/Bash
Varios comandos de la guía original (pensada para Linux/macOS) no funcionan tal cual en
PowerShell nativo:
- `curl -L ... | sh -`: no existe `sh` en PowerShell.
- `eval $(minikube docker-env)`: el equivalente es `minikube docker-env | Invoke-Expression`.
- El contenedor `istio-proxy` (imagen `proxyv2`) no incluye `curl` — para consultar la API de
  administración de Envoy desde dentro del propio sidecar hay que usar
  `pilot-agent request GET stats` en su lugar.

## 7. Estado actual (última actualización: fase canary)

- Completadas y verificadas funcionando: servicios-base, mTLS estricto, traffic routing,
  canary deployment (90/10).
- Pendientes: circuit breaker (Fase 6, `outlierDetection` en `productos-destination-rule`),
  Kiali dashboard (Fase 7).
- Herramienta `hey` (generador de carga) aún no instalada — se necesitará para las pruebas de
  circuit breaker.
