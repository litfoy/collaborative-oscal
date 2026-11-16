# Collaborative OSCAL

Read this README in [English](README.md).

Collaborative OSCAL ist ein Open-Source-Projekt für eine selbst hostbare
Plattform zur Zusammenarbeit an Sicherheitskontrollen und Compliance.

[OSCAL](https://pages.nist.gov/OSCAL/) ist ein vom NIST entwickelter Standard,
mit dem sich Sicherheitskataloge, Profile und Bewertungen maschinenlesbar
beschreiben und zwischen Organisationen und Werkzeugen austauschen lassen.
OSCAL bildet die gemeinsame Datengrundlage des Projekts.

## Ziel und aktueller Umfang

Das Ziel ist, verschiedene Rollen dabei zu unterstützen, Sicherheitskontrollen
gemeinsam zu verwalten und zu bewerten, Doppelarbeit zu reduzieren und künftig
Compliance-Prüfungen stärker zu automatisieren.

Der aktuelle Funktionsumfang ist bewusst begrenzt: OIDC-Anmeldung,
mandantenbezogene Zugriffsrechte, ein lesender OSCAL-Katalog-Explorer, die
einfache Erstellung von OSCAL-Profilen und ein Register zur Selbstauskunft über
die Umsetzung von Kontrollen. Kataloge können über die Kommandozeile importiert
werden.
Katalogbearbeitung, Profilauflösung, Assessments, Workflows und Evidenzverwaltung
sind noch nicht implementiert.

## Status: Proof of Concept

Die Software ist ein Proof of Concept, kein produktionsreifes Werkzeug. Ein
großer Teil des Codes wurde agentisch erstellt und bislang nur begrenzt geprüft.
Für produktive Nutzung wären unter anderem umfassende Reviews, Härtung und
Betriebskonzepte erforderlich.

Wir freuen uns über Mitwirkende und Förderer, die das Projekt fachlich,
technisch oder finanziell unterstützen möchten. Eine lokale Demo lässt sich mit
`docker compose up` starten und ist unter [http://localhost:3000](http://localhost:3000)
erreichbar. Sie ist nur für lokale Vorführungen gedacht und darf nicht öffentlich
bereitgestellt oder mit Produktivdaten betrieben werden.

Über die Sprachauswahl im Kopfbereich können Sie zwischen **English**
(Standardeinstellung) und **Deutsch** wechseln. Der Browser merkt sich Ihre
Auswahl; beide Sprachen sind im selben Image enthalten. Übersetzt wird nur die
Oberfläche, niemals importierter OSCAL-Inhalt oder selbst verfasste Beschreibungen.

Hinweise zu Setup, Entwicklung und technischen Details stehen im
[Entwicklerleitfaden](docs/development.md).
