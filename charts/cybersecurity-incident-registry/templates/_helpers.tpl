{{- define "cir.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 40 | trimSuffix "-" -}}
{{- end -}}
{{- define "cir.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "cir.name" .) | trunc 52 | trimSuffix "-" -}}
{{- end -}}
{{- define "cir.labels" -}}
app.kubernetes.io/name: {{ include "cir.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{- end -}}
{{- define "cir.selector" -}}
app.kubernetes.io/name: {{ include "cir.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "cir.image" -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}
{{- end -}}
{{- define "cir.dataClaim" -}}
{{- default (printf "%s-data" (include "cir.fullname" .)) .Values.persistence.existingClaim -}}
{{- end -}}
{{- define "cir.pgClaim" -}}
{{- default (printf "%s-postgres-data" (include "cir.fullname" .)) .Values.database.internal.persistence.existingClaim -}}
{{- end -}}
{{- define "cir.containerSecurity" -}}
runAsNonRoot: true
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
seccompProfile:
  type: RuntimeDefault
{{- end -}}
{{- define "cir.validate" -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" .Values.image.digest) -}}
{{- fail "image.digest must be the immutable sha256 OCI index digest that passed BOTH architecture production gates; PENDING_HOTFIX_REBUILD is not deployable" -}}
{{- end -}}
{{- if not .Values.existingSecret -}}{{- fail "existingSecret must name a pre-created CIR Secret" -}}{{- end -}}
{{- if and (gt (int .Values.replicaCount) 1) (ne .Values.persistence.accessMode "ReadWriteMany") -}}
{{- fail "More than one CIR replica requires ReadWriteMany storage" -}}{{- end -}}
{{- if and .Values.route.enabled (ne .Values.platform "openshift") -}}{{- fail "route.enabled requires platform=openshift" -}}{{- end -}}
{{- if and .Values.route.enabled .Values.ingress.enabled -}}{{- fail "Choose either Route or Ingress" -}}{{- end -}}
{{- if and .Values.ingress.enabled (or (not .Values.ingress.host) (not .Values.ingress.tlsSecret)) -}}
{{- fail "Production Ingress requires ingress.host and ingress.tlsSecret" -}}{{- end -}}
{{- if eq .Values.database.mode "internal" -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" .Values.database.internal.image.digest) -}}
{{- fail "Internal PostgreSQL requires a verified PostgreSQL 18 Debian image digest" -}}{{- end -}}
{{- if not .Values.database.internal.existingSecret -}}{{- fail "Internal PostgreSQL requires its pre-created existingSecret" -}}{{- end -}}
{{- end -}}
{{- end -}}
