# Plan — Console step 4 : Vulnerability et Exposure

> Plan approuvé, copié tel quel. L'avancement et les décisions prises depuis (API ciblée, bundle cron reporté, recalcul coalescé, permissions de l'acceptation de risque) sont dans [`console-step-4-status.md`](console-step-4-status.md) et les décisions 44 à 53 de `cadrage.md`.

## Contexte

Tu m'as demandé de finir la console : steps 4, 5, 6 et 1b. Chacun aura son plan à valider, au fil de l'eau ; celui-ci
couvre le **step 4**.

Les steps 1 à 3 ont livré l'inventaire normalisé :
- `inventory_package` : purl, type, namespace, name, version, direct ou transitif ;
- les applications, les hôtes et les images ;
- l'événement `InventoryProcessed`.

Les contextes `Vulnerability` et `Exposure` sont encore vides, et rien ne dit à une équipe ce qui est vulnérable, en fin
de vie ou en retard.

**Tes choix** :
- OSV via l'**API ciblée** : seuls les paquets réellement inventoriés sont interrogés ;
- planification : **les commandes seulement**, le bundle cron viendra plus tard ;
- un Finding **par application**, et des Findings d'hôte pour l'OS ;
- périmètre : **vulnérabilités, fins de vie, obsolescence, acceptation de risque**.

**Hors de ce step** :
- dashboards par équipe, projet et environnement (step 5) ;
- notifications et digests (step 6) ;
- export SBOM et VEX.

## Décisions par défaut (à corriger si besoin)

1. **Confidentialité OSV** :
   - on n'envoie à osv.dev que des couples (écosystème, nom) : jamais une version, un hôte ni une équipe ;
   - la comparaison des versions se fait en local, sur les advisories stockées.
2. **Écosystème OSV d'un paquet** :
   - déduit du purl : `composer` → `Packagist`, `npm` → `npm` ;
   - pour les paquets OS, du qualifier `distro` : `deb` + `debian-12` → `Debian:12`, `Ubuntu:24.04:LTS`, `apk` + `alpine-3.20` → `Alpine:v3.20`, `rpm` → `AlmaLinux:9` / `Rocky Linux:9` / `Red Hat` ;
   - sans `distro`, le paquet n'est pas évaluable : il est compté, jamais deviné.
3. **Paquets OS et paquet source** :
   - OSV indexe Debian, Alpine et RPM par **paquet source** (`openssl`), alors que l'inventaire contient les binaires (`libssl3`) ;
   - **ajout additif au protocole v1 (§8.5)** : un composant OS porte le qualifier purl `upstream=<paquet source>`, comme syft, quand il diffère du binaire ;
   - la recherche se fait par `upstream`, sinon par le nom.
4. **Versions** :
   - un comparateur par écosystème, dans `Vulnerability\Domain` :
     - Composer, via `composer/semver`, requis explicitement ;
     - SemVer 2 pour npm ;
     - dpkg pour Debian et Ubuntu, avec l'époque et le `~` ;
     - apk pour Alpine ;
     - rpmvercmp pour RPM ;
   - une plage OSV (`introduced`, `fixed`, `last_affected`, `limit`, plus la liste `versions`) s'évalue avec le comparateur de l'écosystème.
5. **Sévérité** :
   - score CVSS 3.x calculé depuis le vecteur OSV (formule officielle) ;
   - un vecteur CVSS 4 est stocké, sans score, et la sévérité retombe sur `database_specific.severity` ;
   - **KEV** (flux CISA complet, quotidien) et **EPSS** (API FIRST, par lots de CVE connues) enrichissent l'advisory.
6. **Fins de vie** (endoflife.date, API v1), via une table de correspondance en Domain :
   - runtimes `php` et `nodejs` : faits d'hôte et runtime de l'application ;
   - OS : `debian`, `ubuntu`, `alpine`, `rhel`, `almalinux`, `rocky`, depuis les faits d'hôte ; pour une image, depuis le `distro` de ses paquets ;
   - frameworks : `symfony` (`symfony/http-kernel`), `laravel` (`laravel/framework`), `drupal` (`drupal/core`) ;
   - **niveau du Finding** : `upcoming` à J-180, `soon` à J-90, `imminent` à J-30, puis `expired`. Le niveau est recalculé chaque jour ; les alertes seront envoyées au step 6.
7. **Obsolescence** :
   - seulement pour les dépendances **directes** Composer et npm ;
   - dernière version stable publiée : Packagist `p2` et npm en métadonnées abrégées (`application/vnd.npm.install-v1+json`) ;
   - un Finding `outdated` en retard **majeur** ou **mineur** ; un retard de correctif seul est ignoré.
8. **Finding** :
   - identité : (équipe, sujet `application` | `host`, id du sujet, type `vulnerability` | `eol` | `outdated`, clé) ;
   - clé : id de l'advisory + paquet, produit, ou paquet ;
   - les paquets d'une image comptent pour chaque application qui l'exécute ;
   - statuts :
     - `open` : il réapparaît avec sa date de première détection ;
     - `fixed` : il n'est plus produit ;
     - `accepted` : il garde son état de détection, et il est neutralisé tant que l'acceptation court.
9. **Acceptation de risque** :
   - justification et **expiration obligatoires** ;
   - expiration au plus 1 an après, réglable ensuite ;
   - auditée et révocable ;
   - une acceptation expirée rouvre le Finding (tâche cron) ;
   - permission `finding.accept_risk` sur le projet de l'application ; pour un Finding d'hôte, sur l'équipe (défauts du rôle d'équipe, matrice §7bis) ;
   - `finding.view` suit `InventoryScope` : un `TEAM_GUEST` voit les Findings des applications de ses projets.
10. **Recalcul** :
    - `RefreshFindings(teamId)` recalcule toute l'équipe, de façon idempotente, dans la file `matching` ;
    - l'équipe est le bon grain jusqu'à 200 agents, et la file reste découpable plus tard.
    - Il est déclenché :
      - par `InventoryProcessed` ;
      - par `AdvisoriesUpdated` (index inverse : équipes qui détiennent ces paquets) ;
      - chaque jour, parce que les niveaux de fin de vie bougent avec le temps.

## Fondations (lot 1)

- **Protocole** (`.github`) : qualifier `upstream`, dans §8.5, l'exemple de SBOM et `validate.py`. Le faux agent l'envoie.
- **Planification** : pas de bundle pour l'instant (tu brancheras `lexik/cron-file-generator-bundle` plus tard). Ce step livre uniquement les commandes console et leurs cibles `make`, prêtes à être planifiées.
- **Messenger** :
  - nouveaux transports `feeds` (appels externes ; `sync` est déjà le transport `sync://`) et `matching`, en Doctrine et en `sync://` en test ;
  - le service `worker` consomme `ingest matching feeds`.
- **Contrats Shared** :
  - `ListTeamComponents(teamId)` (Inventory) : par sujet, ses composants, ceux de l'image comptés pour l'application, plus les runtimes et l'OS des faits ;
  - `ListWatchedPackages` ;
  - `FindTeamsUsing(ecosystem, names)`.

## Vulnerability (lots 2 à 4)

- **Domain** :
  - `Advisory` : id OSV, alias, résumé, publication et modification, retrait, CVSS (vecteur et score), sévérité, `affected` (valeur), références, KEV (date d'ajout), EPSS (score et percentile) ;
  - `AdvisoryPackage` : index (écosystème, nom) → advisory ;
  - `WatchedPackage` : (écosystème, nom), date de dernière synchro ;
  - `EolProduct` / `EolCycle` ;
  - `LatestRelease` : (écosystème, nom), dernière version stable, date ;
  - comparateurs de versions, `OsvRange`, `CvssV3`.
- **Synchro** (commandes Application ; ports `OsvClient`, `KevFeed`, `EpssClient`, `EndOfLifeClient`, `ReleaseRegistry` ; adaptateurs HttpClient en Infrastructure, avec timeouts et retries) :
  - `SyncPackages(list)` :
    - OSV `/v1/querybatch` par paquet sans version, pagination `next_page_token` ;
    - puis `/v1/vulns/{id}` seulement pour les advisories nouvelles ou modifiées ;
    - publie `AdvisoriesUpdated`.
  - À chaque `InventoryProcessed`, les nouveaux paquets surveillés sont synchronisés tout de suite (file `sync`).
  - Toutes les 6 h : tous les paquets surveillés, par lots.
  - Une fois par jour : KEV, EPSS, endoflife.date, dernières versions.
  - Commandes : `make vuln-sync`, `make eol-sync`, `make releases-sync`.

## Exposure (lots 5 et 6)

- **Domain** :
  - `Finding` : équipe, sujet, type, clé, purl, version installée, versions corrigées, sévérité, KEV, EPSS, niveau EOL, statut, dates de première et dernière détection, date de correction ;
  - `RiskAcceptance` : Finding, justification, auteur, expiration, révocation ;
  - `FindingCalculator` (pur) : composants, advisories, cycles, dernières versions → Findings attendus.
- **Application** :
  - `RefreshFindings` : différence avec l'existant (ouvrir, corriger, mettre à jour, rouvrir) ;
  - `AcceptRisk` et `RevokeRiskAcceptance` (audités) ;
  - `ExpireRiskAcceptances` (cron) ;
  - requêtes `ListFindings(teamId, subject)` et `GetFinding`.
- **Interface** (le minimum, le dashboard viendra au step 5) :
  - un onglet ou une table **Findings** sur les pages application et hôte : type, sévérité ou niveau, paquet, installé → corrigé, KEV et EPSS, statut ;
  - la page d'une advisory : alias, résumé, références, applications touchées dans l'équipe ;
  - le dialogue **Accept risk** (justification, expiration) et **Revoke**.
- **Effacement** : `TeamContentEraser` (une équipe supprimée emporte ses Findings).

## Découpage en commits (un `make qa` vert avant chacun)

1. `.github` : qualifier `upstream` au protocole. Console : fondations (transports, `composer/semver`, faux agent).
2. Comparateurs de versions, plages OSV et CVSS 3.x (Domain pur, vecteurs de test).
3. Synchro OSV (paquets surveillés, advisories), KEV et EPSS.
4. Synchro endoflife.date et dernières versions Packagist / npm.
5. Exposure : Findings et recalcul (vulnérabilités, fins de vie, obsolescence), déclencheurs.
6. Acceptation de risque, expiration et interface des Findings.
7. Documentation :
   - `cadrage.md`, décisions 44 et suivantes ;
   - `design.md` ;
   - plan et statut du step 4 ;
   - `CLAUDE.md`.

## Tests

- **Unitaires, 100 % de MSI** :
  - comparateurs, avec des tables de vecteurs pour chaque écosystème (`dpkg --compare-versions`, rpmvercmp, apk et SemVer officiels) ;
  - plages OSV et CVSS 3.1 (exemples du standard) ;
  - écosystème OSV d'un purl ;
  - calculateur de Findings (vulnérabilité, `upstream`, fin de vie aux seuils, obsolescence majeure ou mineure, correctif ignoré) ;
  - cycle de vie d'un Finding et acceptation de risque.
- **Fixtures** : vraies réponses OSV, KEV, EPSS, endoflife.date, Packagist et npm enregistrées, servies par `MockHttpClient`. Jamais de réseau en test.
- **Fonctionnels** :
  - un inventaire produit des Findings visibles sur l'application et sur l'hôte ;
  - une nouvelle advisory ouvre un Finding ;
  - un inventaire corrigé le passe en `fixed` ;
  - acceptation et révocation ;
  - vue d'un `TEAM_GUEST` ;
  - refus sans `finding.accept_risk`.
- **Intégration** : index inverse, unicité des Findings, effacement d'équipe.

## Vérification

1. `make qa` vert, avec 100 % de MSI, à chaque commit.
2. Dev :
   - `make fleet-fake-agent a=inventory`, puis `make vuln-sync eol-sync releases-sync` (réseau réel) ;
   - l'application de démo montre des Findings ;
   - accepter un risque, puis le révoquer ;
3. Steps suivants, chacun avec son plan : step 5 (dashboards), step 6 (notifications), step 1b (passkeys).
