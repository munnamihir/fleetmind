{{- define "fleetmind.name" -}}
fleetmind
{{- end }}

{{- define "fleetmind.labels" -}}
app.kubernetes.io/name: {{ include "fleetmind.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{- define "fleetmind.databaseEnv" -}}
{{- if .Values.database.existingSecret }}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.database.existingSecret }}
      key: {{ .Values.database.urlKey }}
{{- else }}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Release.Name }}-fleetmind
      key: DATABASE_URL
{{- end }}
{{- end }}
