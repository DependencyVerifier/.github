# Plan — Console step 5 : dashboards

> Plan approuvé, copié tel quel. L'avancement est dans [`console-step-5-status.md`](console-step-5-status.md), les décisions dans `cadrage.md` (54 à 57).

## Contexte

Le step 4 calcule les Findings, mais on ne les voit que sur une page application ou une page hôte. Rien ne dit à une
équipe, à un projet ou à un environnement où il est exposé ni ce qui presse (MVP §10.6, cadrage §8 « Dashboard »).

**Tes choix** :
- des dashboards à 4 niveaux : **équipe, projet, environnement, hôte** ;
- les graphiques avec **symfony/ux-chartjs** ;
- trois blocs : **répartition des Findings**, **applications les plus exposées**, **calendrier des fins de vie** ;
- une **liste des Findings de l'équipe, avec des filtres**.

**Hors de ce step** :
- la matrice des composants par environnement ;
- les notifications (step 6) ;
- l'export.

## Décisions par défaut (à corriger si besoin)

1. **Findings dénormalisés pour la lecture** : au recalcul, un Finding copie :
   - le nom de son sujet (nom de l'application, nom d'hôte) ;
   - l'environnement et le projet de l'application (`null` pour un hôte ou une application non rattachée).
   
   Les dashboards et la liste filtrent ainsi en SQL, dans Exposure, sans appel à un autre contexte par ligne.
   - `TeamSubject` reçoit `name` et `environmentId` ; Exposure obtient le projet par `ListTeamEnvironments` (Organization).
   - Inventory publie `ApplicationPlacementChanged(teamId)` au rattachement et au détachement d'une application. Exposure le traite comme `InventoryChanged` (recalcul coalescé).
2. **Visibilité**, reprise de `FindingAccess` :
   - un membre qui voit tous les projets voit tout ;
   - un `TEAM_GUEST` ne voit que les Findings des projets qu'il voit : filtre SQL sur `project_id`, et jamais ceux du parc.
3. **Montée de version conseillée** :
   - pour une fin de vie, le matching ajoute le cycle le plus récent encore supporté (« PHP 8.2 → 8.5 ») ;
   - stocké sur le Finding (`suggested`).
4. **Chiffres d'un périmètre** (équipe, projet, environnement ou hôte), dans une requête `GetExposureSummary(teamId, scope, id)` :
   - Findings ouverts non acceptés, par sévérité, avec KEV à part ;
   - fins de vie par niveau ;
   - dépendances en retard ;
   - Findings acceptés ;
   - Findings ouverts et corrigés par jour sur 30 jours ;
   - les 5 applications les plus exposées, classées par KEV, puis critiques, puis hautes ;
   - le calendrier des fins de vie : produit, cycle, date, niveau, cycle conseillé et nombre de sujets, trié par date.
5. **Graphiques** :
   - un donut des sévérités et une courbe ouverts / corrigés sur 30 jours ;
   - les couleurs viennent des variables CSS du thème (`--sev-*`, et une variante sombre), lues par un contrôleur Stimulus TypeScript qui étend celui de ux-chartjs ;
   - aucun attribut `style`, la CSP reste stricte ;
   - les chiffres restent toujours visibles en texte : le graphique n'est qu'un complément, et les lecteurs d'écran ont le texte.
6. **Pages** :
   - **équipe** :
     - nouvelle section **Findings** dans la barre latérale (`/teams/{t}/findings`) : dashboard en tête, puis la liste ;
     - la vue d'ensemble garde une frame compacte avec les sévérités, à côté des compteurs Inventory ;
   - **projet** :
     - nouvelle section **Findings** dans le groupe du projet (`/teams/{t}/projects/{p}/findings`) : dashboard et liste du projet ;
     - une frame de synthèse sur la vue d'ensemble du projet ;
   - **environnement** :
     - nouvelle page `/teams/{t}/projects/{p}/environments/{e}` : dashboard, applications de l'environnement, Findings ;
     - le nom de l'environnement dans l'onglet Environments y mène ;
   - **hôte** : une frame de synthèse (sévérités et fins de vie) en tête de la page hôte.
7. **Liste filtrée** :
   - `FindingsTable` est généralisée avec une colonne **Sujet** (nom, lien vers l'application ou l'hôte) ;
   - filtres en `<select>` dans l'en-tête de la table, transmis à la requête par le contrôleur DataTable : type, sévérité, statut (ouvert / accepté / corrigé ; ouvert par défaut), projet pour l'équipe, environnement pour le projet ;
   - la recherche porte sur le titre, le paquet, les identifiants et le sujet.

## Lots (un `make qa` vert avant chaque commit)

1. **Chart.js** :
   - `make composer c='req symfony/ux-chartjs'`, puis `docker compose exec node yarn install` (paquet `@symfony/ux-chartjs` en `file:vendor/…`) ;
   - contrôleur `assets/controllers/exposure_chart_controller.ts` (thème, accessibilité, pas de légende décorative) ;
   - `make typecheck` vert.
2. **Dénormalisation** :
   - `TeamSubject` (`name`, `environmentId`) ;
   - événement `ApplicationPlacementChanged` ;
   - colonnes du Finding (`subject_name`, `environment_id`, `project_id`, `suggested`) et migration ;
   - `Risk::suggested` dans `RiskAssessor` ;
   - un recalcul ultérieur remplit les colonnes des Findings existants (`make findings-refresh`).
3. **Lecture Exposure** :
   - `GetExposureSummary` (DBAL : agrégats, série sur 30 jours, top 5, calendrier) ;
   - `ListTeamFindings(teamId, filters, PageRequest)` ;
   - visibilité par `FindingAccess`.
4. **Interface** :
   - section Findings d'équipe et de projet ;
   - frames de synthèse (vue d'ensemble de l'équipe et du projet, page hôte), sur le modèle de `TeamInventoryFrameView` ;
   - page environnement (Organization pour le cadre, Inventory pour les applications avec un filtre `environmentId` dans `ListApplications`, Exposure pour le dashboard) ;
   - barre latérale et `TeamTabsTest`.
5. **Documentation** :
   - `cadrage.md`, décisions 54 et suivantes ;
   - `design.md` ;
   - plan et statut du step 5 ;
   - `CLAUDE.md`.

## Fichiers clés

- **Modifiés** :
  - `src/Exposure/Domain/Model/Finding.php` ;
  - `src/Exposure/Application/Command/Refresh/Handler/RefreshFindingsHandler.php` ;
  - `src/Shared/Application/Contract/Inventory/TeamSubject.php` ;
  - `src/Inventory/Infrastructure/Doctrine/DbalInventoryReadModel.php` (`teamSubjects`, filtre d'environnement) ;
  - `src/Vulnerability/Application/Assessment/RiskAssessor.php` ;
  - `templates/components/AppSidebar.html.twig`.
- **À réutiliser** :
  - `FindingAccess` ;
  - `FindingsTable` et ses cellules ;
  - `shared/frame/lazy.html.twig`, `FrameEndpoint`, et `TurboFrame` d'Exposure (même motif qu'Inventory) ;
  - `SeverityBadge`, `MetaGrid` ;
  - `InventoryPage` et `TeamPage` pour le cadre.

## Tests (100 % de MSI)

- **Unitaires** :
  - dénormalisation au recalcul (nom, environnement, projet, mise à jour au rattachement) ;
  - `suggested` (cycle le plus récent supporté, aucun si tout est en fin de vie) ;
  - visibilité de la synthèse et de la liste (membre, `TEAM_GUEST`, autre équipe) ;
  - filtres.
- **Intégration** : agrégats SQL (sévérités, série sur 30 jours, top 5, calendrier) sur des Findings construits.
- **Fonctionnels** :
  - section Findings d'équipe et de projet avec filtres ;
  - page environnement ;
  - frames de synthèse ;
  - un `TEAM_GUEST` voit son projet seulement ;
  - les données du graphique sont dans le HTML.

## Vérification

1. `make qa` vert à chaque commit.
2. Dev : `make findings-refresh`, puis, de ton côté dans le navigateur :
   - le dashboard de l'équipe (donut, courbe, top 5, calendrier) ;
   - la liste filtrée ;
   - la page environnement ;
   - la synthèse sur la page hôte.
