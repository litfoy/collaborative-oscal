# Collaborative OSCAL

**Gemeinsame Compliance-Daten. Unabhängige Bewertungen.**

[English](README.md) · [Architektur](docs/architecture/overview.md) · [AI-Governance-Demo](docs/architecture/ai-governance-demo-seed.md)

Collaborative OSCAL ist eine unabhängige, Open-Source-GRC-Plattform für kollaborative Governance-, Risiko- und Compliance-Prozesse, die sich selbst betreiben lässt. Das Projekt befindet sich in der Alpha-Entwicklung und verwendet [NIST OSCAL (Open Security Controls Assessment Language)](https://pages.nist.gov/OSCAL/) als native gemeinsame Informationsgrundlage.

Das Projekt soll redundante Governance- und Compliance-Arbeit in den Bereichen Datenschutz, Informationssicherheit, KI-Sicherheit, AI Governance und weiteren Governance-Domänen reduzieren. Gemeinsame Systeminformationen, Schutzmaßnahmen und Umsetzungsdaten können domänenübergreifend wiederverwendet werden, während Anforderungen, Verantwortlichkeiten und Prüfurteile jeder Domäne unabhängig bleiben.

Die zentrale Idee: **Umsetzungen dort, wo es sinnvoll ist, einmal dokumentieren, Informationen regelwerksübergreifend wiederverwenden und im jeweiligen fachlichen Kontext unabhängig bewerten.** OSCAL dient dabei als gemeinsame maschinenlesbare Datengrundlage und nicht lediglich als Exportformat.

![Collaborative OSCAL](./assets/Collaborative%20OSCAL%20Governance%20Blueprint.png)

*Konzeptioneller Überblick: gemeinsame Schutzmaßnahmen und Systeminformationen, getrennte Prüfungen. Unabhängige Feststellungen werden auf Datenmodellebene unterstützt; gemeinsame Nachweisverwaltung und differenzierte Stakeholder-Berechtigungen sind noch geplant.*

> **Alpha-Status:** Noch nicht für den Produktivbetrieb, vertrauliche Daten oder verbindliche Compliance-Entscheidungen vorgesehen. Die Implementierung bietet noch keine vollständige differenzierte Funktionstrennung, keine komplette Lifecycle-Abdeckung und keine abschließende operative Härtung.

## Motivation

Organisationen müssen häufig überlappende Anforderungen aus unterschiedlichen Standards, regulatorischen Vorgaben und internen Richtlinien berücksichtigen. Verschiedene Stakeholder betrachten dasselbe System, dieselbe technische Konfiguration oder dieselbe organisatorische Maßnahme, verfolgen jedoch unterschiedliche Prüfziele und können zu unterschiedlichen Bewertungen gelangen.

Collaborative OSCAL unterscheidet drei Ebenen:

- **Anforderungen:** Jeder normative oder organisationsspezifische Katalog behält seine Identität, seinen Inhalt und seine Revisionshistorie. Explizite Mappings beschreiben Beziehungen, ohne Compliance-Bewertungen gleichzusetzen.
- **Umsetzung:** Wiederverwendbare Maßnahmen, konkrete Systemkomponenten und anforderungsspezifische Umsetzungsbeiträge werden getrennt betrachtet. Eine Umsetzung kann zu mehreren Anforderungen beitragen, ohne diese automatisch zu erfüllen.
- **Prüfung:** Prüfpläne, Beobachtungen und Feststellungen behalten ihren jeweiligen Prüfumfang und historischen Kontext. Eine dokumentierte Umsetzung ist kein Nachweis ihrer Wirksamkeit; eine Feststellung bestimmt nicht automatisch das Ergebnis einer anderen Prüfung.

Die langfristige Vision ist eine gemeinsame Informationsgrundlage mit expliziter Wiederverwendung geeigneter Nachweise, klaren Verantwortlichkeiten und unabhängiger Bewertungshoheit. Dies ist insbesondere für Organisationen mit mehreren Governance- und Kontrollfunktionen relevant, auch in regulierten Branchen.

Mögliche Regelwerke sind BSI IT-Grundschutz++, DSGVO, ISO/IEC 27001 und 27002, NIST SP 800-53, NIST AI RMF, ISO/IEC 42001, der EU AI Act sowie interne Richtlinien. Voraussetzung sind geeignete OSCAL-Inhalte und entsprechende Nutzungsrechte. Dies sind angestrebte Anwendungsfälle, keine Aussage über vollständige Regelwerksabdeckung oder regulatorische Konformität.

### Beispiel: Multifaktor-Authentifizierung

Ein Informationssicherheitsbeauftragter (ISB) prüft den Schutz privilegierter Zugänge. Ein Datenschutzbeauftragter (DSB) betrachtet die Sicherheit der Verarbeitung personenbezogener Daten nach Art. 32 DSGVO. Beide können dieselbe MFA-Maßnahme und denselben Identity Provider referenzieren, dokumentieren aber separate Beiträge zu ihren jeweiligen Anforderungen und führen getrennte Prüfungen durch.

Perspektivisch könnten beide denselben geeigneten, versionierten Konfigurationsexport oder dasselbe Testprotokoll ausdrücklich wiederverwenden und dennoch unterschiedliche Feststellungen treffen. MFA allein begründet keine Konformität mit Art. 32 DSGVO.

## Schnellstart

Voraussetzung ist Docker Compose v2 oder neuer. Im Repository-Verzeichnis:

```bash
docker compose up --build -d credentials db db-init api web
```

Alternativ lässt sich der Stack mit dem optionalen AI-Governance-Demodatensatz starten:

```bash
docker compose --profile ai-governance-demo up --build -d
```

Die Anwendung ist unter [http://localhost:3000](http://localhost:3000) erreichbar. Die Standarddemo enthält einen NIST-SP-800-53-Katalog. Für den lokalen Demomodus ist kein externer Identity Provider erforderlich.

**Nur für lokale Demonstrationen:** Alle Personen mit Zugriff auf die Demo-Oberfläche verwenden dieselbe Demo-Identität. Die Demo darf weder öffentlich bereitgestellt noch mit produktiven oder vertraulichen Daten betrieben werden. Die Oberfläche ist auf Englisch und Deutsch verfügbar; die Sprachauswahl übersetzt weder importierte OSCAL-Inhalte noch selbst verfasste Texte.

Der [Entwicklerleitfaden](docs/development.md) beschreibt Einrichtung, Konfiguration und Tests. Hinweise zum Seed-Status, zur Fehlersuche und zu bestehenden Demo-Installationen finden sich in der [AI-Governance-Dokumentation](docs/architecture/ai-governance-demo-seed.md).

## AI-Governance-Demo

Die optionale Demo beschreibt eine fiktive interne Plattform für KI-gestützte Softwareentwicklung anhand ausgewählter Controls aus einem OSCAL-Katalog auf Grundlage des [NIST AI RMF Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence).

Das Szenario verbindet die Versionierung von Modellen und Datensätzen, menschliche Aufsicht (Human Oversight), Acceptable Use Policies, Risikomessung und AI Red Teaming mit wiederverwendbaren Schutzmaßnahmen, konkreten Komponenten und anforderungsspezifischen Umsetzungsbeiträgen. Es umfasst einen versionierten Systemsicherheitsplan (SSP), einen Prüfplan (AP) und Prüfergebnisse (AR).

Eine beispielhafte Feststellung betrifft die Nachvollziehbarkeit von Modellversionen: Zwei von drei stichprobenartig geprüften fiktiven Release-Datensätzen erfüllen ein lokales Prüfziel, einer nicht. Die Feststellung bezieht sich ausschließlich auf dieses Prüfziel und trifft keine Aussage über den Status des gesamten Controls oder der übrigen geplanten Controls.

Das Szenario demonstriert Dokumentation und Prüfung, nicht den Betrieb einer KI-Agentenplattform. Alle Szenariodaten und Nachweislinks sind fiktiv. Es stellt weder einen realen Compliance-Nachweis noch eine Zertifizierung oder automatisierte KI-Sicherheitsprüfung dar.

Weitere Informationen: [Szenario und Seed-Dokumentation](docs/architecture/ai-governance-demo-seed.md) und [Herkunft des Katalogs](examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.provenance.json).

## Aktueller Funktionsumfang

Alle implementierten Funktionen befinden sich in experimenteller Alpha-Qualität.

| Bereich | Funktion | Status |
| --- | --- | --- |
| Anforderungskataloge | Import, hierarchische Darstellung und unveränderliche Quellrevisionen | Implementiert |
| Anforderungsprofile | Explizite Control-Auswahl aus verschiedenen Katalogrevisionen | Implementiert; vollständige Auflösung zurückgestellt |
| Anforderungszuordnungen | Explizite katalogübergreifende Beziehungen; keine automatische Compliance-Ableitung | Implementiert |
| Komponentendefinitionen | Wiederverwendbare Schutzmaßnahmen und Controls | Implementiert |
| Umsetzungsregister | Anforderungsspezifische Umsetzungsbeiträge | Implementiert |
| Systeme | Konkrete Systemkomponenten | Implementiert |
| Systemsicherheitspläne (SSP) | Katalogbasierte SSP, Validierung und unveränderliche Dokumentversionen | Implementiert |
| Prüfpläne (AP) | Prüfumfang, Prüfziele, Prüfgegenstände, Aktivitäten, Aufgaben, Rollen sowie fest referenzierter SSP-/SSP-Versionskontext | Implementiert |
| Prüfergebnisse (AR) | Menschlich erstellte oder importierte geprüfte Controls, Beobachtungen, Nachweisreferenzen, Feststellungen und fest referenzierte AP-Versionen | Implementiert |
| Automatisierte Prüfung | Mandantenbezogene REST-Übermittlung nativer OSCAL-1.2.1-Prüfergebnis-JSON-Dokumente in den Prüfergebnis-Lebenszyklus | Implementiert |
| Menschliche und automatisierte Prüfungen | Beide folgen demselben Arbeitsstand-, Veröffentlichungs-, Validierungs- und Historienmodell, bei dem eine Veröffentlichung einen unveränderlichen Snapshot erzeugt, während der Arbeitsstand für nachfolgende Änderungen bearbeitbar bleibt | Implementiert |
| Historische Integrität | Importierte Katalogrevisionen und veröffentlichte SSP-, AP- und AR-Dokumentstände sind unveränderlich. Eine Veröffentlichung erzeugt einen unveränderlichen historischen Snapshot, während der Arbeitsstand für nachfolgende Änderungen bearbeitbar bleibt. Importierte Prüfergebnis-Arbeitsstände bleiben bis zur ersten Veröffentlichung bearbeitbar. Historische Referenzen bleiben an den ursprünglichen Dokumentstand gebunden. | Implementiert |
| Optimistische Nebenläufigkeit | Implementiert für Prüfpläne, Prüfergebnisse, SSPs, Profile und Mapping-Sammlungen. Unabhängig geprüft und akzeptiert für Prüfpläne, Prüfergebnisse und SSPs; Profile und Mapping-Sammlungen warten auf unabhängige Prüfung | Implementierung für diese Aggregate vorhanden; unabhängige Prüfung für Profile und Mapping-Sammlungen ausstehend |
| SBOM-Sichtbarkeit in der CI | Automatisierte CycloneDX-SBOM-Erzeugung für API- und Web-Abhängigkeiten in Entwicklungs- und Laufzeitumfang | In der CI implementiert |
| Gemeinsame Prüfnachweise | Verwaltete, versionierte Nachweisbibliothek und prüfungsübergreifende Wiederverwendung | Langfristiger Plan |

Die authentifizierte REST-API akzeptiert native OSCAL-Prüfergebnis-JSON-Dokumente für die automatisierte Prüfungseingabe. Der Import verwendet dasselbe Aggregate, dieselbe Validierung, denselben fest referenzierten Prüfplan-Kontext und denselben Veröffentlichungs-Lebenszyklus wie der manuelle Arbeitsplatz. Siehe [REST-Import von Prüfergebnissen](docs/assessment-result-import.md). Nachweise werden derzeit als OSCAL-Nachweisreferenzen abgebildet, nicht als verwaltete Dateiablage.

Weitere Funktionen sind OIDC-Authentifizierung, mandantenbezogene Autorisierung, englisch- und deutschsprachige Oberflächen sowie OSCAL-JSON-Import und/oder -Export, soweit das jeweilige Dokumentmodell dies unterstützt. Die Validierung verwendet gepflegte OSCAL-Modelle und geeignete offizielle NIST-Schemas je OSCAL-Version sowie anwendungsspezifische Integritätsprüfungen.

## Architektur

Die Anwendung ist als modularer Monolith mit Next.js / TypeScript im Frontend, FastAPI / Python im Backend und PostgreSQL zur Datenhaltung aufgebaut. Sie verwendet [Compliance Trestle](https://github.com/oscal-compass/compliance-trestle), OpenID Connect und Docker Compose.

Zentrale Architekturentscheidungen:

- Importierte Katalogrevisionen und veröffentlichte SSP-, AP- und AR-Dokumentversionen sind unveränderlich. Eine Veröffentlichung erzeugt einen unveränderlichen historischen Snapshot, während der Arbeitsstand für nachfolgende Änderungen bearbeitbar bleibt. Importierte Prüfergebnis-Arbeitsstände bleiben bis zur ersten Veröffentlichung bearbeitbar. Historische Referenzen bleiben an den ursprünglichen Dokumentstand gebunden.
- Wiederverwendbare Maßnahmen, konkrete Komponenten und anforderungsspezifische Umsetzungsbeiträge bleiben getrennt. Mappings übertragen weder Umsetzungsstatus noch Prüfergebnisse automatisch.
- PostgreSQL verbindet maßgebliche OSCAL-JSONB-Dokumentstände mit relationalen Identitäten, Mandantengrenzen und expliziten Referenzen. Bearbeitbare Arbeitsstände ermöglichen Änderungen vor der Erstellung einer Dokumentversion.
- Die OSCAL-Verarbeitung folgt einem Trestle-first-Ansatz, ergänzt durch offizielle versionsspezifische NIST-JSON-Schemas sowie anwendungsspezifische Referenz- und Integritätsprüfungen. Dies ist keine vollständige semantische OSCAL-Validierung.
- Neue Dokumente verwenden OSCAL 1.2.1, soweit dies der festgelegten Authoring-Strategie entspricht. Importierte und historische Dokumente behalten ihre deklarierte Version und werden nicht stillschweigend konvertiert.

Siehe [Architekturübersicht](docs/architecture/overview.md), [Domänenmodell](docs/architecture/domain-model.md) und [Architecture Decision Records](docs/adr/), insbesondere [SSP](docs/adr/0017-system-security-plans.md), [Prüfpläne](docs/adr/0019-assessment-plans.md) und [Prüfergebnisse](docs/adr/0020-assessment-results.md).

### OSCAL Compass und Compliance Trestle

[OSCAL Compass](https://oscal-compass.dev/) ist ein Open-Source-Projekt unter dem Dach der Cloud Native Computing Foundation (CNCF). Seine Werkzeuge unterstützen die OSCAL-basierte Erstellung, Validierung und Automatisierung von Compliance-Artefakten. Insbesondere stellt [Compliance Trestle](https://github.com/oscal-compass/compliance-trestle) eine CLI und ein SDK zur Verarbeitung von OSCAL-Artefakten bereit, während [Agile Authoring](https://github.com/oscal-compass/compliance-trestle-agile-authoring) kollaborative Erstellung auf Grundlage von GitOps unterstützt.

Eine der ursprünglichen Ideen hinter Collaborative OSCAL war es, möglichst weitgehend auf dem OSCAL-Compass-Ökosystem aufzubauen und dessen Werkzeuge wiederzuverwenden, anstatt die OSCAL-Verarbeitung neu zu entwickeln. Die generierten Modelle und Validierungsfunktionen von Trestle sind über eine eigene Adapterschicht eingebunden ([ADR 0002](docs/adr/0002-oscal-adapter-boundary.md)). Offizielle Schemas und anwendungsspezifische Prüfungen ergänzen sie, wo erforderlich.

Collaborative OSCAL untersucht einen ergänzenden Ansatz: einen browserbasierten, datenbankgestützten Web-Service für Stakeholder, die nicht unbedingt mit Git arbeiten. Maßgebliche Datenquelle für die Compliance-Dokumente ist die Anwendungsdatenbank, nicht ein Git-Repository; GitOps wird für die tägliche Nutzung bewusst nicht vorausgesetzt. Das ist eine Architekturentscheidung für diesen Anwendungsfall, keine Abkehr von GitOps oder Compliance as Code. Git-basierte Workflows und weitergehende Integrationen mit OSCAL-Compass-Werkzeugen können perspektivisch sinnvoll sein. [Compliance to Policy (C2P)](https://github.com/oscal-compass/compliance-to-policy) ist noch nicht integriert.

## Bekannte Einschränkungen und Roadmap

Zu den Alpha-Einschränkungen gehören unvollständige semantische Validierung, differenzierte Stakeholder-Berechtigungen und Funktionstrennung, teilweise noch fehlende Workflow-Abdeckung sowie weitere operative Härtung. Optimistische Nebenläufigkeit ist für Prüfpläne, Prüfergebnisse, SSPs, Profile und Mapping-Sammlungen implementiert; unabhängig überprüfte und verifizierte Nachweise bestehen für Prüfpläne, Prüfergebnisse und SSPs, während Profile und Mapping-Sammlungen auf unabhängige Prüfung warten.

### Kurzfristige Prioritäten

- Die Nebenläufigkeitsabdeckung für die verbleibenden Aggregate abschließen, indem die unabhängige Prüfung und Verifikation für Profile und Mapping-Sammlungen fertiggestellt wird.
- Gemeinsame Verwaltung von Parties, Rollen und Verantwortlichkeiten ergänzen.
- Native OSCAL-Inventaritems und erweiterte Prüfgegenstände implementieren.
- Eine gemeinsame System- und Inventarübersicht bereitstellen.
- Bearbeitbare eigene Kataloge ermöglichen.
- Die Katalogauswahl erweitern und eine domänenübergreifende Governance-Demo bereitstellen.
- Frontend-UX und UI-Arbeitsabläufe konsolidieren.
- Sicherheit, CI/CD und Release-Härtung verbessern.

### Langfristige Pläne

- Gemeinsame, versionierte Prüfnachweise und prüfungsübergreifende Wiederverwendung ergänzen.
- Risikomanagement und POA&M-Workflows ergänzen.
- OSCAL-Interoperabilität, portable Dokumentworkflows und Berichte ausweiten.
- Differenzierte Autorisierung und formale Freigaben erweitern.
- Die semantische Validierung von Prüfzielen, Methoden, Prüfschritten und geprüftem Umfang verbessern.
- Profilauflösung und Parameterbearbeitung weiter ausbauen.

Schema-valide OSCAL-Dokumente belegen weder regulatorische Konformität noch garantieren sie die Interoperabilität mit jedem OSCAL-Werkzeug. Sie beschreiben Daten und Prüfungskontexte und bestimmen nicht das unabhängige Prüfurteil einer Organisation. Siehe [Katalogimport](docs/catalog-import.md), [Entscheidung zur Profilauflösung](docs/adr/0016-defer-profile-resolution.md) und [Interoperabilitätsbefunde zur AI-Governance-Demo](docs/architecture/ai-governance-demo-interoperability-findings-2026-11-17.md).

## Entwicklung und Qualitätssicherung

Die Entwicklung wird vom Menschen geführt und durch KI unterstützt; dabei kommt Agentic Software Engineering in erheblichem Umfang zum Einsatz. Der Gründer und Maintainer des Projekts trifft die Produkt- und Architekturentscheidungen; KI-Werkzeuge unterstützen Implementierung, Spezifikation und technische Prüfung. Reviews werden vom Gründer und Maintainer des Projekts zusammen mit KI-gestützten Reviews durchgeführt. Die Verantwortung für Annahmeentscheidungen und Releases bleibt beim Gründer und Maintainer des Projekts. Automatisierte Tests und Architecture Decision Records unterstützen die Verifikation; es wird nicht behauptet, dass sämtlicher generierter Code manuell geprüft oder unabhängig auditiert wurde.

Das Repository enthält Backend- und Frontend-Tests, PostgreSQL-Integrationstests, eine CI-Konfiguration sowie Kompatibilitäts- und Regressionstests. Die [Kompatibilitätsnotizen zu Prüfergebnissen](docs/architecture/assessment-results-compatibility-probes-2026-11-17.md) dokumentieren weitere während der Entwicklung durchgeführte Prüfungen. Testergebnisse früherer Entwicklungsstände stellen keine Release-Zertifizierung dar; die aktuellen Testsuiten und manuellen Workflows sollten entsprechend dem [Entwicklerleitfaden](docs/development.md) ausgeführt werden.

## Projektbeiträge und Governance

Siehe [CONTRIBUTING.md](CONTRIBUTING.md) für Beitragsrichtlinien, [MAINTAINERS.md](MAINTAINERS.md) für Verantwortlichkeiten der Maintainer und [SECURITY.md](SECURITY.md) für die koordinierte Meldung von Sicherheitslücken. Transparenz bei der Entwicklung und Erwartungen für KI-Unterstützung sind in [AI_USAGE.md](AI_USAGE.md) dokumentiert.

## Danksagung

Collaborative OSCAL baut auf der Arbeit verschiedener Open-Source-Projekte und Communities auf:
- [NIST OSCAL](https://pages.nist.gov/OSCAL/) – der offene Standard, auf dem dieses Projekt basiert.
- [OSCAL Compass](https://github.com/oscal-compass) – ein Ökosystem von Werkzeugen und Ressourcen für OSCAL-basiertes Compliance-Management.
- [Compliance Trestle](https://github.com/oscal-compass/compliance-trestle) – Verarbeitung und Validierung von OSCAL-Dokumenten.
- [OSCAL Compass Content](https://github.com/oscal-compass/oscal-content) – wiederverwendbare OSCAL-Inhalte, darunter der in unserer Demo verwendete NIST AI RMF Generative AI-Katalog.
- Unser Dank gilt den Maintainern und Contributors dieser Projekte sowie der zahlreichen Open-Source-Bibliotheken, die Collaborative OSCAL ermöglichen.
- Das Projekt profitiert außerdem vom fachlichen Austausch innerhalb der LF AI & Data Security & Compliance Working Group.
- Collaborative OSCAL ist ein unabhängiges Projekt und weder offiziell mit NIST, OSCAL Compass oder der Linux Foundation verbunden noch von diesen Organisationen offiziell unterstützt.

## Lizenz

Die selbst entwickelte Software steht unter der [Apache License 2.0](LICENSE). Hinweise zur Projektzuordnung stehen in der Datei [NOTICE](NOTICE).

Für Kataloge Dritter, Schemas, Test-Fixtures, Abhängigkeiten und Container-Inhalte gelten weiterhin deren jeweilige Lizenz- und Namensnennungspflichten; die Softwarelizenz lizenziert diese Inhalte nicht um. Siehe:

- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- [docs/license-compliance-assessment.md](docs/license-compliance-assessment.md)
- [docs/npm-license-inventory.json](docs/npm-license-inventory.json)
- [docs/python-license-inventory.runtime.json](docs/python-license-inventory.runtime.json)

Projekt-eigene Dokumentation steht unter [Creative Commons Attribution 4.0 International](LICENSES/CC-BY-4.0.txt) (CC-BY-4.0).

CC-BY-4.0-Geltungsbereich in diesem Repository:

- Root-Dokumentation: `README.md`, `README.de.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `MAINTAINERS.md` und `AI_USAGE.md`
- Projekt-eigene Markdown-Dateien unter `docs/`, sofern eine Datei nicht eindeutig Rechte Dritter oder abweichende Lizenzbedingungen ausweist

Vom CC-BY-4.0-Geltungsbereich ausgenommen:

- Software-Quellcode und Skripte (Apache-2.0)
- Drittanbieter-Artefakte, übernommene normative Inhalte, Schemas, Fixtures und Provenance-Dateien (ursprüngliche Lizenzen bleiben gültig)
- Maschinen-generierte Abhängigkeitsinventare in `docs/`

## Weiterführende Informationen

- [NIST OSCAL](https://pages.nist.gov/OSCAL/)
- [OSCAL Compass](https://oscal-compass.dev/) · [GitHub](https://github.com/oscal-compass)
- [Compliance-Trestle-Dokumentation](https://oscal-compass.github.io/compliance-trestle/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [LF AI & Data](https://lfaidata.foundation/)
- [BSI – Stand-der-Technik-Bibliothek](https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek)
