# Collaborative OSCAL

**Gemeinsame Compliance-Daten. Unabhängige Bewertungen.**

[English](README.md) · [Architektur](docs/architecture/overview.md) · [AI-Governance-Demo](docs/architecture/ai-governance-demo-seed.md)

Collaborative OSCAL ist ein selbst betreibbarer Open-Source-Proof-of-Concept für kollaborative Governance-, Risiko- und Compliance-Prozesse (GRC) auf Grundlage von [NIST OSCAL (Open Security Controls Assessment Language)](https://pages.nist.gov/OSCAL/).

Das Projekt untersucht, wie Informationssicherheit, Datenschutz, AI Governance, Risikomanagement, Compliance, Systemverantwortliche und Auditoren auf einer gemeinsamen Informationsgrundlage zusammenarbeiten können, ohne ihre jeweiligen Anforderungen, Verantwortlichkeiten und fachlichen Bewertungen aufzugeben.

Die zentrale Idee: **Umsetzungen dort, wo es sinnvoll ist, einmal dokumentieren, Informationen regelwerksübergreifend wiederverwenden und im jeweiligen fachlichen Kontext unabhängig bewerten.** OSCAL dient dabei als gemeinsame maschinenlesbare Datengrundlage und nicht lediglich als Exportformat.

![Collaborative OSCAL](./assets/Collaborative%20OSCAL%20Governance%20Architecture.png)

*Konzeptioneller Überblick: gemeinsame Maßnahmen und Systeminformationen, getrennte Prüfungen. Unabhängige Feststellungen werden auf Datenmodellebene unterstützt; eine gemeinsame Nachweisbibliothek und differenzierte Stakeholder-Berechtigungen sind noch geplant.*

> **Projektstatus: Experimenteller Proof of Concept.** Nicht für den Produktivbetrieb, vertrauliche Daten oder verbindliche Compliance-Entscheidungen vorgesehen. Die Implementierung demonstriert den Ansatz, setzt die vollständige Funktionstrennung der Stakeholder aber noch nicht technisch durch.

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

Voraussetzung ist eine funktionsfähige Docker-Installation mit Docker Compose. Im Repository-Verzeichnis:

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

Alle implementierten Funktionen sind experimentell.

| Bereich | Funktion | Status |
| --- | --- | --- |
| Anforderungskataloge | Import, hierarchische Darstellung, unveränderliche Quellrevisionen | Implementiert |
| Anforderungsprofile | Explizite Control-Auswahl aus verschiedenen Katalogrevisionen | Implementiert; vollständige Auflösung zurückgestellt |
| Anforderungszuordnungen | Explizite katalogübergreifende Beziehungen; keine automatische Compliance-Ableitung | Implementiert |
| Komponentendefinitionen | Wiederverwendbare Maßnahmen und Controls | Implementiert |
| Umsetzungsregister | Anforderungsspezifische Beiträge und Verantwortlichkeiten | Implementiert |
| Systeme | Konkrete Systemkomponenten | Implementiert |
| Systemsicherheitspläne (SSP) | Katalogbasierte SSP, Validierung, unveränderliche Dokumentversionen | Implementiert |
| Prüfpläne (AP) | Prüfumfang, Prüfziele, Prüfgegenstände, Aktivitäten, Aufgaben, Rollen, fest referenzierte SSP-Versionen | Implementiert |
| Prüfergebnisse (AR) | Geprüfte Controls, Beobachtungen, Nachweisreferenzen, Feststellungen, fest referenzierte AP-Versionen | Implementiert |
| Unabhängige Prüfungen | Getrennte Prüfpläne, Ergebnisse und Feststellungen im jeweiligen Kontext | Auf Datenmodellebene implementiert; differenzierte Autorisierung offen |
| Gemeinsame Prüfnachweise | Versionierte Nachweisbibliothek und prüfungsübergreifende Wiederverwendung | Geplant |
| Risiken und POA&M | Risikobehandlung, Planung und Nachverfolgung von Verbesserungsmaßnahmen | Geplant |

Darüber hinaus unterstützt die Anwendung OIDC-Authentifizierung, mandantenbezogene Autorisierung, deutsche und englische Oberflächen sowie OSCAL-JSON-Import und/oder -Export entsprechend dem jeweiligen Dokumentmodell. Nachweise in Prüfergebnissen bestehen derzeit aus Referenzen, nicht aus einer verwalteten Dateiablage.

## Architektur

Die Anwendung ist als modularer Monolith mit Next.js / TypeScript im Frontend, FastAPI / Python im Backend und PostgreSQL zur Datenhaltung aufgebaut. Sie verwendet [Compliance Trestle](https://github.com/oscal-compass/compliance-trestle), OpenID Connect und Docker Compose.

Zentrale Architekturentscheidungen:

- Importierte Katalogrevisionen und veröffentlichte SSP-, AP- und AR-Dokumentversionen sind unveränderlich. Historische Referenzen bleiben an den ursprünglichen Dokumentstand gebunden.
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

Der POC demonstriert einen Workflow vom Anforderungskatalog bis zum Prüfergebnis, keinen vollständigen Compliance-Management-Lebenszyklus. Insbesondere:

- Die semantische Validierung muss verbessert werden: rekursive Erkennung normativer Prüfziele und Statements, Abbildung lokaler Prüfmethoden, stabile Prüfschrittidentitäten und der Umfang tatsächlich geprüfter Objectives erfordern Korrekturen oder Erweiterungen.
- Differenzierte Stakeholder-Berechtigungen, Funktionstrennung, formale Freigaben und robuste gleichzeitige Bearbeitung sind noch nicht umgesetzt. Die vorhandene mandantenbezogene Autorisierung darf nicht mit unabhängiger Bewertungshoheit gleichgesetzt werden.
- Gemeinsame, versionierte Nachweisverwaltung, strukturierte Nachweisherkunft sowie Risiko- und POA&M-Workflows bleiben zukünftige Arbeitspakete.
- Die vollständige Profilauflösung wurde nach Kompatibilitätstests bewusst zurückgestellt. SSP referenzieren derzeit direkt eine Katalogrevision. Die Festlegung und Auflösung von Parametern muss weiterentwickelt werden.
- Strukturierte Erstellung eigener Kataloge, portable Dokumentpakete, menschenlesbare Berichte und breitere Interoperabilitätstests sind geplant oder erfordern weitere Entwicklung.

Schema-valide OSCAL-Dokumente belegen weder regulatorische Konformität noch garantieren sie die Interoperabilität mit jedem OSCAL-Werkzeug. Siehe [Katalogimport](docs/catalog-import.md), [Entscheidung zur Profilauflösung](docs/adr/0016-defer-profile-resolution.md) und [Interoperabilitätsbefunde zur AI-Governance-Demo](docs/architecture/ai-governance-demo-interoperability-findings-2026-11-17.md).

## Entwicklung und Qualitätssicherung

Sehr große Teile der Software sind durch agentische Softwareentwicklung (Agentic Coding) entstanden, vorwiegend mit GitHub Copilot, durch iterative Prompt-Präzisierung und zunehmend konkrete Aufgabenspezifikationen. ChatGPT unterstützte Konzeption, Spezifikation und kritische Reviews. Menschliche Entscheidungen, Überprüfung und Freigaben, dokumentierte Architekturentscheidungen und reproduzierbare Tests bleiben wesentliche Bestandteile des Entwicklungsprozesses. KI-generierte Erklärungen und Code gelten nicht allein deshalb als verifiziert, weil sie plausibel erscheinen.

Das Repository enthält Backend- und Frontend-Tests, PostgreSQL-Integrationstests, eine CI-Konfiguration sowie Kompatibilitäts- und Regressionstests. Die [Kompatibilitätsnotizen zu Prüfergebnissen](docs/architecture/assessment-results-compatibility-probes-2026-11-17.md) dokumentieren weitere während der Entwicklung durchgeführte Prüfungen. Testergebnisse früherer Entwicklungsstände stellen keine Release-Zertifizierung dar; die aktuellen Testsuiten und manuellen Workflows sollten entsprechend dem [Entwicklerleitfaden](docs/development.md) ausgeführt werden.

## Danksagung und Community
Collaborative OSCAL ist ein unabhängiges persönliches Open-Source-Projekt. Es ist kein offizielles Projekt von OSCAL Compass, CNCF, LF AI & Data oder NIST. Eine Unterstützung durch diese Organisationen  wird damit nicht behauptet.

## Lizenz

Die selbst entwickelte Software steht unter der [Apache License 2.0](LICENSE). Für Kataloge Dritter und andere externe Inhalte gelten deren jeweilige Lizenzen und Namensnennungspflichten; die Softwarelizenz lizenziert diese Inhalte nicht um.

## Weiterführende Informationen

- [NIST OSCAL](https://pages.nist.gov/OSCAL/)
- [OSCAL Compass](https://oscal-compass.dev/) · [GitHub](https://github.com/oscal-compass)
- [Compliance-Trestle-Dokumentation](https://oscal-compass.github.io/compliance-trestle/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [LF AI & Data](https://lfaidata.foundation/)
- [BSI – Stand-der-Technik-Bibliothek](https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek)
v