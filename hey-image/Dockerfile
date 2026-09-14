FROM golang:1.24-alpine AS build
RUN go install github.com/rakyll/hey@latest

FROM alpine:3.19
COPY --from=build /go/bin/hey /usr/local/bin/hey
ENTRYPOINT ["hey"]