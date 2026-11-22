# Collaborative OSCAL

**Gemeinsame Compliance-Daten. Unabhängige Bewertungen.**

[English](README.md) · [Architektur](docs/architecture/overview.md) · [AI-Governance-Demo](docs/architecture/ai-governance-demo-seed.md)

Collaborative OSCAL ist eine unabhängige, selbst hostbare Open-Source-Plattform für die Zusammenarbeit in Governance, Risk und Compliance (GRC). Das Projekt befindet sich in der **Alpha-Entwicklung** und verwendet [NIST OSCAL (Open Security Controls Assessment Language)](https://pages.nist.gov/OSCAL/) als natives Informationsmodell – nicht lediglich als Import- und Exportformat.

Das Ziel ist, redundante Arbeit in Datenschutz, Informationssicherheit, KI-Sicherheit, AI Governance und weiteren Governance-Domänen zu reduzieren. Darüber hinaus wird eine API zur Automatisierung von Compliance angeboten. Informationen zu Systemen, Schutzmaßnahmen und Umsetzungen lassen sich dort wiederverwenden, wo dies fachlich sinnvoll ist. Anforderungen, Verantwortlichkeiten und Prüfurteile bleiben dabei eigenständig.

**Umsetzungen dort, wo es sinnvoll ist, einmal dokumentieren, geeignete Informationen regelwerksübergreifend wiederverwenden und jede Anforderung im eigenen Kontext unabhängig bewerten.**

![Collaborative OSCAL](./assets/Collaborative%20OSCAL%20Governance%20Framework.png)

*Konzeptioneller Überblick: gemeinsame Schutzmaßnahmen und Systeminformationen, getrennte Prüfungen. Unabhängige Feststellungen werden im Datenmodell unterstützt; eine gemeinsame Nachweisverwaltung und differenzierte Stakeholder-Berechtigungen sind noch geplant.*

> **Alpha-Status:** Collaborative OSCAL ist nicht für den Produktivbetrieb, vertrauliche Daten oder verbindliche Compliance-Entscheidungen vorgesehen. Ein unabhängiges Sicherheitsaudit und die für produktive GRC-Software erforderliche Härtung und Funktionstrennung sind noch nicht abgeschlossen. Es wird weder Produktionsreife noch regulatorische Konformität behauptet.

## Motivation

Organisationen müssen Anforderungen aus verschiedenen Standards, Gesetzen und internen Richtlinien berücksichtigen. Unterschiedliche Fachdisziplinen können dasselbe System oder dieselbe Schutzmaßnahme betrachten, dabei aber verschiedene Mandate, Prüfkriterien und Ergebnisse haben.

Collaborative OSCAL trennt drei Ebenen:

- **Anforderungen:** Quellkataloge und ihre Revisionen behalten ihre Identität. OSCAL Profiles wählen Controls für einen Betrachtungsumfang aus; diese Auswahl begründet noch keine rechtliche Anwendbarkeit. Explizite katalogübergreifende Mappings beschreiben Beziehungen, ohne Gleichwertigkeit zu unterstellen.
- **Umsetzung:** Wiederverwendbare Komponentendefinitionen, konkrete Systemkomponenten und anforderungsspezifische Implementierungen sind unterschiedliche Konzepte. Eine Schutzmaßnahme kann mehrere Controls unterstützen, ohne diese automatisch zu erfüllen.
- **Prüfung:** Prüfpläne und Prüfergebnisse behalten ihren eigenen Umfang, ihre Beobachtungen, Feststellungen und historischen Referenzen. Eine dokumentierte Umsetzung ist kein Wirksamkeitsnachweis, und ein Prüfurteil bestimmt nicht automatisch ein anderes.

Langfristig soll eine gemeinsame Informationsgrundlage mit expliziter Wiederverwendung geeigneter Nachweise, klaren Verantwortlichkeiten und unabhängiger Bewertungshoheit entstehen.

Mögliche Anwendungsbereiche sind BSI IT-Grundschutz++, DSGVO, ISO/IEC 27001 und 27002, NIST SP 800-53, NIST AI RMF, ISO/IEC 42001, der EU AI Act und interne Richtlinien – sofern geeignete OSCAL-Inhalte mit entsprechenden Nutzungsrechten vorliegen. Dies ist **keine** Zusage vollständiger Regelwerksabdeckung oder regulatorischer Konformität.

### Beispiel: Multifaktor-Authentifizierung

Ein Informationssicherheitsbeauftragter prüft privilegierte Zugriffe. Ein Datenschutzbeauftragter betrachtet die Sicherheit personenbezogener Datenverarbeitung nach Art. 32 DSGVO. Beide können dieselbe MFA-Maßnahme und denselben Identity Provider referenzieren, dokumentieren jedoch eigenständige Beiträge und kommen gegebenenfalls zu unterschiedlichen Prüfurteilen.

Eine künftige gemeinsame Nachweisbibliothek könnte die ausdrückliche Wiederverwendung desselben geeigneten, versionierten Konfigurationsexports oder Testprotokolls ermöglichen. MFA allein begründet keine DSGVO-Konformität.

## Schnellstart

Mit Docker Compose v2 oder neuer im Repository-Verzeichnis ausführen:

```bash
docker compose up --build -d
```

Die Anwendung ist unter [http://localhost:3000](http://localhost:3000) erreichbar. Beim lokalen Start werden der Acme-Workspace initialisiert, der NIST-SP-800-53-Basiskatalog importiert und der AI-Governance-/Governance-Coverage-Seed angewendet, bevor API und Webanwendung starten. Der Seed enthält NIST-GenAI- und EU-AI-Act-Kataloge, Demo-Mappings und fiktive Systeme. Ein externer Identity Provider ist im lokalen Demomodus nicht erforderlich.

**Nur für lokale Demonstrationen:** Alle Personen mit Zugang zur Demo-Oberfläche handeln unter derselben Demo-Identität. Der Modus darf nicht öffentlich erreichbar sein und nicht mit realen, produktiven oder vertraulichen Daten betrieben werden. Die Oberfläche unterstützt Deutsch und Englisch; die Sprachauswahl übersetzt weder importierte OSCAL-Inhalte noch selbst verfasste Texte.

Der Compliance Explorer ist über die Anwendungsnavigation erreichbar. Er benötigt ein Informationssystem und **ein bis fünf bereits vorhandene Profiles**. Der standardmäßige Governance-Seed erstellt noch keine direkt auswählbaren Explorer-Profile; diese müssen zunächst erstellt oder ausgewählt werden. Die explorative Auswahl eines Profiles bedeutet nicht, dass dieses für das ausgewählte System verbindlich oder anwendbar ist.

Einrichtung und Tests beschreibt der [Entwicklerleitfaden](docs/development.md). Informationen zu Seed-Verhalten und Fehlerbehebung bietet die [AI-Governance-Dokumentation](docs/architecture/ai-governance-demo-seed.md). Bereits vorhandene lokale Demodaten sollten nicht ohne Prüfung der Folgen zurückgesetzt werden.

## AI-Governance-Demo

Das enthaltene Szenario beschreibt eine **fiktive** interne Plattform für KI-gestützte Softwareentwicklung mit ausgewählten Controls aus einem OSCAL-Katalog auf Grundlage des [NIST AI RMF Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence).

Es verbindet Modell- und Datensatzversionierung, menschliche Aufsicht (Human Oversight), Acceptable Use Policies, Risikomessung und AI Red Teaming mit wiederverwendbaren Schutzmaßnahmen, konkreten Komponenten und anforderungsspezifischen Umsetzungsbeiträgen. Das Szenario enthält einen versionierten Systemsicherheitsplan (SSP), einen Prüfplan (AP) und Prüfergebnisse (AR).

Eine beispielhafte Feststellung betrifft die Nachvollziehbarkeit von Modellversionen: Zwei von drei fiktiven Release-Datensätzen erfüllen ein lokales Prüfziel, einer nicht. Diese Feststellung bezieht sich **auf das konkrete Prüfziel**, nicht automatisch auf das gesamte Control oder andere Anforderungen.

Die Governance-Coverage-Erweiterung ergänzt EU-AI-Act-Controls und explizite katalogübergreifende Demo-Mappings. Mapping-Beziehungen sind keine fachlich bestätigten Aussagen regulatorischer Gleichwertigkeit. Das Szenario ist keine laufende KI-Agentenplattform; alle Daten und Nachweislinks sind fiktiv. Es belegt weder Compliance noch Zertifizierung oder tatsächliche KI-Sicherheitsleistung.

Siehe [Szenario- und Seed-Dokumentation](docs/architecture/ai-governance-demo-seed.md) und [Katalog-Provenienz](examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.provenance.json).

## Aktueller Funktionsumfang

Alle Funktionen haben experimentellen Alpha-Status. Es wird nicht jeder OSCAL-Bestandteil oder Workflow vollständig unterstützt.

| Bereich | Implementierter Funktionsumfang oder Status |
| --- | --- |
| Anforderungskataloge | Import, hierarchische Darstellung und unveränderliche Quellrevisionen. |
| Anforderungsprofile | Explizite Control-Auswahl aus mehreren gepinnten Katalogrevisionen; vollständige OSCAL Profile Resolution ist zurückgestellt. |
| Anforderungszuordnungen | Explizite katalogübergreifende Beziehungen ohne automatische Gleichwertigkeits- oder Compliance-Ableitung. |
| Komponentendefinitionen | Wiederverwendbare Schutzmaßnahmen als OSCAL Component Definitions. |
| Systeme und Umsetzungsregister | Informationssysteme, konkrete Systemkomponenten und anforderungsspezifische Implementierungen. |
| Compliance Explorer (C-light) | **Lesende** Requirements- und Measures-Ansichten für ein ausgewähltes System und ein bis fünf Profiles. Identische Quell-Controls werden zusammengeführt, ihre Profile-Mitgliedschaften bleiben sichtbar; nur explizit mit dem System verknüpfte Implementierungen werden angezeigt. |
| Systemsicherheitspläne (SSP) | Katalogbasierte Pläne, Validierung, explizite Implementation-Mitgliedschaften und unveränderliche veröffentlichte Dokumentversionen. |
| Prüfpläne (AP) | Prüfumfang, Prüfziele, Prüfgegenstände, Aktivitäten, Aufgaben, Rollen und Referenzen auf historische SSP-Versionen. |
| Prüfergebnisse (AR) | Menschlich erstellte oder importierte geprüfte Controls, Beobachtungen, Nachweisreferenzen und Feststellungen mit Verweisen auf historische AP-Versionen. |
| Assessment-Automatisierung | Authentifizierter, mandantenbezogener REST-Import unterstützter nativer OSCAL-1.2.1-Assessment-Results-JSON-Dokumente in den bestehenden Arbeits- und Veröffentlichungslebenszyklus. |
| Veröffentlichung und Historie | Änderbare Arbeitsstände mit unveränderlichen publizierten SSP-/AP-/AR-Snapshots und gepinnten historischen Referenzen. |
| Optimistische Nebenläufigkeit | Aggregatbezogener Schutz implementiert und abgenommen für APs, ARs, SSPs, Profiles, Mapping Collections, Component Definitions, Information Systems, einzelne System Components und Control Implementations (einschließlich Responsibilities). |
| Supply-Chain-Transparenz | CycloneDX-Abhängigkeits-SBOMs für Python/API und npm/Web, jeweils Laufzeit- und Entwicklungsabhängigkeiten; Erzeugung in der CI konfiguriert. |
| Gemeinsame Nachweisverwaltung | Verwaltete, versionierte Dateiablage mit prüfungsübergreifender Wiederverwendung: **nicht implementiert**. |
| Risiko- und POA&M-Management | Eigenständige Prozesse zur Risikobehandlung und Maßnahmenverfolgung: **nicht implementiert**. |

Die **Measures View** des Compliance Explorers gruppiert nur Controls der aktuell geladenen, serverseitig paginierten Seite; sie ist noch keine vollständige, global paginierte Maßnahmenübersicht. Der Explorer zeigt weder Prüfurteile noch katalogübergreifende Mappings, berechnet keine Compliance-Scores, leitet keine Anwendbarkeit ab und erzeugt keine dauerhafte System/Profile-Zuordnung. Controls ohne systembezogene Implementation erscheinen als **für dieses System nicht dokumentiert** – nicht automatisch als nicht konform.

Der native REST-Import von OSCAL Assessment Results nutzt dieselbe Arbeitsstandsvalidierung, den gepinnten AP-Kontext und den Veröffentlichungslebenszyklus wie manuell erstellte Prüfergebnisse. Nachweise werden derzeit als OSCAL-Referenzen abgebildet, nicht als verwaltete Dateien. Siehe [REST-Import von Prüfergebnissen](docs/assessment-result-import.md).

Weitere Funktionen sind OIDC-Authentifizierung, mandantenbezogene Autorisierung, eine deutsch- und englischsprachige Oberfläche sowie nativer OSCAL-JSON-Import/-Export für unterstützte Dokumentmodelle. Die Validierung verbindet gepflegte OSCAL-Modelle, geeignete offizielle NIST-Schemas und anwendungsspezifische Integritätsprüfungen; sie deckt nicht jede denkbare semantische Bedingung ab.

## Architektur

Collaborative OSCAL ist ein **modularer Monolith** mit Next.js / React / TypeScript im Frontend, Python / FastAPI im Backend, SQLAlchemy und PostgreSQL als Persistenz sowie einem Browser-BFF. OpenID Connect und Docker Compose werden unterstützt.

Zentrale Architekturprinzipien:

- **OSCAL First:** OSCAL-Konzepte, Identitäten und Dokumentsemantik möglichst erhalten. Anwendungsspezifische Persistenz-, Autorisierungs- und Arbeitsstandsbelange bleiben separat.
- **Historische Unveränderlichkeit:** Importierte Katalogrevisionen und publizierte SSP-/AP-/AR-Snapshots sind unveränderlich. Änderungen an gemeinsamen Daten schreiben historische Veröffentlichungen nicht um. Arbeitsstände können zwischen Publikationen weiterentwickelt werden.
- **Explizite Referenzen:** Profile-Auswahlen, Katalogrevisionen, Mappings, Systemkomponenten und Implementierungen besitzen typisierte, überprüfbare Beziehungen. Gleiche Titel bedeuten keine identischen Entitäten.
- **Unabhängige Prüfungen:** Gemeinsame Schutzmaßnahmen, Systemkomponenten oder Implementierungen begründen weder gleichwertige Anforderungen noch identische Prüfergebnisse.
- **Nebenläufigkeit und Mandantentrennung:** Änderbare Aggregate verwenden – soweit implementiert – den vereinbarten Optimistic-Concurrency-Vertrag und mandantenbezogene Autorisierung. Konfliktbehandlung im Frontend darf ungespeicherte Arbeit nicht stillschweigend verwerfen.
- **Wiederverwenden statt Neuerfinden:** OSCAL-Verarbeitung mit Compliance Trestle hinter einer Adaptergrenze, offiziellen versionsspezifischen NIST-JSON-Schemas und eigenen Integritätsprüfungen.

Neue Dokumente verwenden im Regelfall OSCAL 1.2.1 entsprechend der unterstützten Authoring-Strategie. Importierte und historische Dokumente behalten ihre deklarierte Version und werden nicht stillschweigend konvertiert.

Siehe [Architekturübersicht](docs/architecture/overview.md), [Domänenmodell](docs/architecture/domain-model.md), [Architecture Decision Records](docs/adr/), [Concurrency-ADR](docs/adr/0022-aggregate-optimistic-concurrency.md), [SSP-ADR](docs/adr/0017-system-security-plans.md), [AP-ADR](docs/adr/0019-assessment-plans.md) und [AR-ADR](docs/adr/0020-assessment-results.md).

### Warum Python? OSCAL Compass und Compliance Trestle

Python wurde **bewusst** als Backend-Sprache gewählt, um das bestehende OSCAL-Tooling-Ökosystem, insbesondere [Compliance Trestle](https://github.com/oscal-compass/compliance-trestle), nutzen zu können, statt eine separate OSCAL-Verarbeitung aufzubauen oder die Technologie allein nach der bisherigen Sprachpraxis des Maintainers auszuwählen.

[OSCAL Compass](https://oscal-compass.dev/) stellt Open-Source-Werkzeuge für OSCAL-basiertes Authoring, Validierung und Automatisierung bereit. Trestle bietet eine Python-CLI und ein SDK; [Agile Authoring](https://github.com/oscal-compass/compliance-trestle-agile-authoring) unterstützt kollaborative GitOps-basierte Erstellung. Collaborative OSCAL baut auf diesem Ökosystem auf, ist aber ein **eigenständiges Projekt** und weder Teilprojekt von OSCAL Compass noch eine offiziell unterstützte CNCF-/LF-Initiative.

Die Trestle-Modelle und Validierungsfunktionen sind über eine eigene [Adaptergrenze (ADR 0002)](docs/adr/0002-oscal-adapter-boundary.md) eingebunden und werden durch offizielle OSCAL-Schemas und anwendungsspezifische Referenzprüfungen ergänzt.

Collaborative OSCAL verfolgt ergänzend einen **browserbasierten, datenbankgestützten** Ansatz für Stakeholder, die nicht täglich mit Git arbeiten. Die maßgebliche operative Datenquelle ist die Anwendungsdatenbank, nicht ein Git-Repository. Das ist keine Ablehnung von GitOps oder Compliance as Code. Weitere Integrationen mit OSCAL-Werkzeugen bleiben möglich; [Compliance to Policy (C2P)](https://github.com/oscal-compass/compliance-to-policy) ist derzeit nicht integriert.

## Bekannte Einschränkungen und Roadmap

Das Projekt befindet sich in der Alpha-Entwicklung: Die semantische Validierung ist unvollständig, differenzierte Stakeholder-Berechtigungen und Funktionstrennung fehlen teilweise, mehrere Workflows sind noch nicht vorhanden, und zusätzliche Security- sowie operative Härtung ist erforderlich. Tests und Architekturdokumentation allein belegen keine Produktionsreife.

Die **Aggregate-Level Optimistic Concurrency ist für die oben aufgeführten Aggregate implementiert und abgenommen**. Einzelne ältere Rollout-Statuspassagen in ADRs und Architekturleitfäden wurden noch nicht mit allen abgeschlossenen Implementierungsreviews synchronisiert; der normative Architekturvertrag gilt unverändert.

### Aktuelle und mögliche nächste Arbeiten

Reihenfolge und genauer Umfang stehen unter dem Entscheidungsvorbehalt des Maintainers:

- Den manuellen Akzeptanzdurchlauf des Compliance Explorers mit den fiktiven Demodaten abschließen und anschließend Informationsarchitektur und Frontend-UX verbessern.
- Den Explorer perspektivisch über die seitenbezogene Measures-Gruppierung hinaus erweitern; mögliche Ergänzungen sind ein Control/Profile-Diff und reichhaltigere, explizit belegte domänenübergreifende Beziehungen.
- Gemeinsame Verwaltung von Parties, Rollen und Responsibilities ergänzen.
- Native OSCAL Inventory Items, erweiterte Prüfgegenstände sowie eine System-/Inventarübersicht einführen.
- Benutzerfreundliches Authoring eigener OSCAL-Kataloge mit klarer Identitäts- und Revisionssemantik ermöglichen.
- Die domänenübergreifende Governance-Demo weiter fachlich kuratieren und zulässig verfügbare Kataloginhalte ergänzen.
- Security-, Entwicklungsverifikations-, CI-/Release- und operative Härtung bedarfsorientiert fortsetzen.

### Langfristige Pläne

- Gemeinsame, versionierte Prüfnachweise und explizite prüfungsübergreifende Wiederverwendung.
- Risikomanagement und POA&M-Workflows.
- Verbesserte OSCAL-Interoperabilität, portable Dokumentworkflows und Reporting.
- Feinere Autorisierung, Prüfzuständigkeiten und formale Freigaben.
- Präzisere semantische Validierung von Prüfziel, Methode, Prüfschritten und geprüftem Umfang.
- Weitergehende Profile Resolution und Parameterbearbeitung.

Schema-valide OSCAL-Dokumente beweisen weder regulatorische Konformität noch garantieren sie Interoperabilität mit jedem OSCAL-Werkzeug. Siehe [Katalogimport](docs/catalog-import.md), [Entscheidung zur Profilauflösung](docs/adr/0016-defer-profile-resolution.md) und [Interoperabilitätsbefunde zur AI-Governance-Demo](docs/architecture/ai-governance-demo-interoperability-findings-2026-11-17.md).

### Weg zur Beta

**Beta-Gate:** Es wird keine Beta-Version veröffentlicht, bevor
(1) eine dokumentierte Konsolidierung und Refaktorierung stattgefunden hat(KI-gestützte Arbeit ist zulässig, aber Umfang, Erkenntnisse und
Entscheidungen werden schriftlich festgehalten), und
(2) eine menschliche Prüfung des Ergebnisses durch eine erfahrene Python-/Sicherheitsexpertin oder einen erfahrenen Python-/Sicherheitsexperten außerhalb der Maintainer-Rolle erfolgt ist, wobei die Befunde und die Reaktionen darauf veröffentlicht werden.

## Entwicklung und Qualitätssicherung

Die Entwicklung ist **menschlich geführt und in erheblichem Umfang KI-unterstützt**, einschließlich Agentic Coding Tools. Der Gründer und Maintainer bringt Erfahrung in der **Backend-Entwicklung mit Java und C**, in Softwarearchitektur und Governance mit, beansprucht jedoch **keine umfassende praktische Python-Erfahrung**. Python wurde aus Ökosystem- und Wiederverwendungsgründen bewusst gewählt, wie oben erläutert; KI-Unterstützung ist Teil des Implementierungsprozesses, nicht der Grund für die Sprachwahl.

Die Verantwortung für Produktausrichtung, Architektur, Abnahmen und Releases bleibt beim Maintainer. KI-Werkzeuge unterstützen Spezifikation, Implementierung, Analyse und Reviews. Änderungen werden mittels menschlich verantworteter Prüfung, gezielter automatisierter Tests und dokumentierter Architekturentscheidungen bewertet; **nicht sämtlicher generierter Code wurde unabhängig oder vollständig manuell auditiert**. Weder grüne Tests noch KI-Reviews ersetzen unabhängige Code- und Sicherheitsaudits. Beiträge und unabhängige Reviews erfahrener Python-Entwickler sind ausdrücklich willkommen.

Das Repository enthält Backend- und Frontend-Testsuiten, PostgreSQL-Integrationstests, CI-Konfiguration und reproduzierbare Entwicklungsabläufe. Die [Kompatibilitätsnotizen zu Prüfergebnissen](docs/architecture/assessment-results-compatibility-probes-2026-11-17.md) dokumentieren zusätzliche Entwicklungsprüfungen. Historische Testberichte sind keine Release-Zertifizierung; die aktuellen Tests und manuellen Abläufe sind im [Entwicklerleitfaden](docs/development.md) beschrieben. Weitere Regeln zur KI-Nutzung stehen in [AI_USAGE.md](AI_USAGE.md).

## Projektbeiträge und Governance

Siehe [CONTRIBUTING.md](CONTRIBUTING.md) für Beitragsrichtlinien, [MAINTAINERS.md](MAINTAINERS.md) für Maintainer-Verantwortlichkeiten und [SECURITY.md](SECURITY.md) für koordinierte Meldungen von Sicherheitslücken. Transparenz über KI-Nutzung und Erwartungen an Contributors sind in [AI_USAGE.md](AI_USAGE.md) dokumentiert.

## Danksagung

Collaborative OSCAL baut auf der Arbeit vieler Open-Source-Projekte und Communities auf:

- [NIST OSCAL](https://pages.nist.gov/OSCAL/) – der zugrunde liegende offene Standard.
- [OSCAL Compass](https://github.com/oscal-compass) – Werkzeuge und Ressourcen für OSCAL-basierte Compliance-Workflows.
- [Compliance Trestle](https://github.com/oscal-compass/compliance-trestle) – Verarbeitung und Validierung von OSCAL-Dokumenten.
- [OSCAL Compass Content](https://github.com/oscal-compass/oscal-content) – wiederverwendbare Inhalte, darunter der NIST AI RMF Generative AI-Katalog der Demo.
- Den Maintainern, Contributors und weiteren Open-Source-Bibliotheken, die das Projekt ermöglichen.
- Dem fachlichen Austausch in der LF AI & Data Security & Compliance Working Group.

Collaborative OSCAL ist unabhängig und weder offiziell mit NIST, OSCAL Compass, CNCF oder der Linux Foundation verbunden noch von diesen Organisationen offiziell unterstützt.

## Lizenz

Die selbst entwickelte Software steht unter der [Apache License 2.0](LICENSE). Hinweise zur Projektzuordnung stehen in [NOTICE](NOTICE).

Für Kataloge, Schemas, Fixtures, Dependencies und Container-Inhalte Dritter gelten weiterhin deren jeweilige Lizenzen und Namensnennungspflichten. Die Softwarelizenz lizenziert solche Inhalte **nicht** um. Siehe:

- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- [docs/license-compliance-assessment.md](docs/license-compliance-assessment.md)
- [docs/npm-license-inventory.json](docs/npm-license-inventory.json)
- [docs/python-license-inventory.runtime.json](docs/python-license-inventory.runtime.json)

Projekteigene Dokumentation steht unter [Creative Commons Attribution 4.0 International](LICENSES/CC-BY-4.0.txt) (CC-BY-4.0), darunter die Root-Dateien `README.md`, `README.de.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `MAINTAINERS.md`, `AI_USAGE.md` sowie eigene Markdown-Dateien unter `docs/`, soweit nicht anders gekennzeichnet.

Von dieser Dokumentationslizenz ausgenommen sind Software und Skripte (Apache-2.0), Inhalte Dritter und übernommene normative Texte (mit deren jeweiligen Lizenzen), Schemas, Fixtures, Provenienzdateien und maschinell erzeugte Abhängigkeitsinventare unter `docs/`.

## Weiterführende Informationen

- [NIST OSCAL](https://pages.nist.gov/OSCAL/)
- [OSCAL Compass](https://oscal-compass.dev/) · [GitHub](https://github.com/oscal-compass)
- [Compliance-Trestle-Dokumentation](https://oscal-compass.github.io/compliance-trestle/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [LF AI & Data](https://lfaidata.foundation/)
- [BSI – Stand-der-Technik-Bibliothek](https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek)
