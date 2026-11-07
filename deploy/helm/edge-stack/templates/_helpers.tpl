{{/*
Chart name, overridable.
*/}}
{{- define "edge-stack.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified release name.
*/}}
{{- define "edge-stack.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "edge-stack.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "edge-stack.labels" -}}
helm.sh/chart: {{ include "edge-stack.chart" . }}
app.kubernetes.io/name: {{ include "edge-stack.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: edge-stack
{{- end }}

{{- define "edge-stack.selectorLabels" -}}
app.kubernetes.io/name: {{ include "edge-stack.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Render a pinned image reference: repository:tag@sha256:digest.
The schema requires the digest, but fail here too so that a value passed on
the command line cannot silently bypass the schema.
*/}}
{{- define "edge-stack.image" -}}
{{- $image := . -}}
{{- if not $image.digest }}
{{- fail "every image must be pinned with a sha256 digest" }}
{{- end }}
{{- printf "%s:%s@%s" $image.repository $image.tag $image.digest }}
{{- end }}
