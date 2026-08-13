---
name: start-qa
description: Entry-point alias for the generate-qa-from-test-cases workflow. Use when the user explicitly invokes $start-qa or asks to start, initialize, resume, or onboard QA for the current project.
---

# Iniciar QA

Usar la skill registrada `generate-qa-from-test-cases` como fuente autoritativa del flujo.

1. Localizar `generate-qa-from-test-cases` en el catálogo de skills disponible.
2. Leer su `SKILL.md` completo y seguir sus instrucciones, referencias y controles de seguridad.
3. Buscar `qa-project.yaml` y `qa-knowledge/` en el proyecto o workspace actual.
4. Si no existen, indicar que es la primera inicialización, no un error, y continuar en la misma respuesta con la primera pregunta del onboarding: “¿Tenés acceso al código fuente?”.
5. Hacer una sola pregunta de onboarding por vez. No detenerse solamente después de informar que falta la configuración.
6. Si la configuración existe, resumirla sin secretos y continuar el flujo desde el primer dato pendiente.
7. Tratar cualquier texto adicional de la invocación como contexto o alcance del proyecto.

Si la skill principal no está instalada, informar claramente que falta `generate-qa-from-test-cases` y solicitar su instalación; no improvisar una versión parcial del flujo.
