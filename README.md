# ServiceMesh

Tres microservicios FastAPI (`usuarios`, `productos`, `pedidos`) desplegados en
Kubernetes (Minikube) con [Istio](https://istio.io) como service mesh: mTLS automático
entre servicios, traffic splitting para canary deployments, circuit breaker ante fallos,
y visualización del tráfico en tiempo real con Kiali. Tercer proyecto de una serie de
práctica de Kubernetes, tras PulseBoard y FlowPipe.

## Estado

En arranque — cluster y CLIs en preparación, sin código de servicios todavía.

## Estructura

- `usuarios-service/`, `productos-service/`, `pedidos-service/` — código FastAPI de cada
  microservicio.
- `k8s/` — manifiestos de Kubernetes e Istio (Deployments, Services, VirtualService,
  DestinationRule, PeerAuthentication).

## Fases

1. Instalar Istio en Minikube
2. Desplegar los tres servicios
3. mTLS estricto (`PeerAuthentication`)
4. Traffic routing (`VirtualService` + `DestinationRule`)
5. Canary deployment
6. Circuit breaker (`outlierDetection`)
7. Kiali dashboard
