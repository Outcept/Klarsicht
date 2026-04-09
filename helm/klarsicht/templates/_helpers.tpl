{{/*
Expand the name of the chart.
*/}}
{{- define "klarsicht.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "klarsicht.fullname" -}}
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

{{/*
Chart label
*/}}
{{- define "klarsicht.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "klarsicht.labels" -}}
helm.sh/chart: {{ include "klarsicht.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/part-of: klarsicht
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Pod security context — fully overridable via values
*/}}
{{- define "klarsicht.podSecurityContext" -}}
{{- toYaml .Values.podSecurityContext }}
{{- end }}

{{/*
Container security context — fully overridable via values
*/}}
{{- define "klarsicht.containerSecurityContext" -}}
{{- toYaml .Values.containerSecurityContext }}
{{- end }}

{{/*
Agent labels
*/}}
{{- define "klarsicht.agent.labels" -}}
{{ include "klarsicht.labels" . }}
app.kubernetes.io/name: {{ include "klarsicht.name" . }}-agent
app.kubernetes.io/component: agent
{{- end }}

{{/*
Agent selector labels
*/}}
{{- define "klarsicht.agent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "klarsicht.name" . }}-agent
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: agent
{{- end }}

{{/*
Dashboard labels
*/}}
{{- define "klarsicht.dashboard.labels" -}}
{{ include "klarsicht.labels" . }}
app.kubernetes.io/name: {{ include "klarsicht.name" . }}-dashboard
app.kubernetes.io/component: dashboard
{{- end }}

{{/*
Dashboard selector labels
*/}}
{{- define "klarsicht.dashboard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "klarsicht.name" . }}-dashboard
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: dashboard
{{- end }}

{{/*
Postgres labels
*/}}
{{- define "klarsicht.postgres.labels" -}}
{{ include "klarsicht.labels" . }}
app.kubernetes.io/name: {{ include "klarsicht.name" . }}-postgres
app.kubernetes.io/component: postgres
{{- end }}

{{/*
Postgres selector labels
*/}}
{{- define "klarsicht.postgres.selectorLabels" -}}
app.kubernetes.io/name: {{ include "klarsicht.name" . }}-postgres
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: postgres
{{- end }}

{{/*
ServiceAccount name
*/}}
{{- define "klarsicht.serviceAccountName" -}}
{{- include "klarsicht.fullname" . }}
{{- end }}

{{/*
Agent secret name
*/}}
{{- define "klarsicht.agent.secretName" -}}
{{- include "klarsicht.fullname" . }}-agent
{{- end }}

{{/*
Postgres secret name
*/}}
{{- define "klarsicht.postgres.secretName" -}}
{{- include "klarsicht.fullname" . }}-postgres
{{- end }}

{{/*
Postgres service hostname
*/}}
{{- define "klarsicht.postgres.host" -}}
{{- include "klarsicht.fullname" . }}-postgres.{{ .Release.Namespace }}.svc
{{- end }}

{{/*
Database URL — uses external URL if provided, otherwise constructs from internal postgres.
*/}}
{{- define "klarsicht.databaseURL" -}}
{{- if .Values.externalDatabase.url }}
{{- .Values.externalDatabase.url }}
{{- else }}
{{- printf "postgresql://klarsicht:$(POSTGRES_PASSWORD)@%s:5432/klarsicht" (include "klarsicht.postgres.host" .) }}
{{- end }}
{{- end }}

{{/*
Watch namespaces as comma-separated string.
*/}}
{{- define "klarsicht.watchNamespaces" -}}
{{- join "," .Values.agent.watchNamespaces }}
{{- end }}
