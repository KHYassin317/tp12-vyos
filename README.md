# TP 12 – VyOS : Infrastructure as Code et routage déclaratif

## Fichiers
- `desired_state.yaml` : état désiré (interface eth1 + BGP AS 65001).
- `apply_state.py` : calcule le delta avec l'état actuel et l'applique via l'API HTTP de VyOS.
- `requirements.txt` : `requests`, `jinja2`, `pyyaml`.

## Utilisation
```bash
pip install -r requirements.txt
export VYOS_HOST=192.168.1.1      # PowerShell : $env:VYOS_HOST="192.168.1.1"
export VYOS_KEY=VotreCleAPI       # PowerShell : $env:VYOS_KEY="VotreCleAPI"
python apply_state.py --dry-run   # voir le delta sans rien appliquer
python apply_state.py             # appliquer
```
La clé API n'est jamais écrite dans le code (variable d'environnement) pour ne pas la publier sur Git.

## Tableau récapitulatif des commandes

| Commande | Rôle | Résultat attendu |
|---|---|---|
| `configure` | Entrer en mode configuration (VyOS) | Prompt `[edit]` |
| `set service https api keys id api-user key VotreCleAPI` | Créer la clé de l'API HTTP | Clé enregistrée (en attente de commit) |
| `commit` | Appliquer la configuration | Pas d'erreur affichée |
| `save` | Sauvegarder dans `config.boot` | `Saving configuration to '/config/config.boot'...` |
| `pip install -r requirements.txt` | Installer requests, jinja2, pyyaml | `Successfully installed ...` |
| `python apply_state.py --dry-run` | Afficher le delta sans l'appliquer | Liste des `set`/`delete` prévus |
| `python apply_state.py` (1ère fois) | Appliquer l'état désiré | `N modification(s)` puis commit + save OK |
| `show bgp summary` (CLI VyOS) | Vérifier la session BGP | Voisin 10.0.12.2, état `Established` (si l'autre routeur est configuré) |
| Modification manuelle (ex. `set protocols bgp neighbor 10.0.12.2 remote-as 65099`, `commit`) | Simuler une dérive | Config différente du YAML |
| `python apply_state.py` (après dérive) | Corriger uniquement l'écart | 1 seule modification : `remote-as` remis à 65002 |
| `python apply_state.py` (2e fois) | Vérifier l'idempotence | `Aucun changement` |

## Note : détection et correction de la dérive
À chaque exécution, le script lit l'état réel du routeur via `/retrieve` (`returnValue`, `returnValues`, `showConfig`, `exists`) et le compare au YAML :
- valeur différente (ex. `remote-as`, `system-as`) → un `set` corrige la valeur ;
- élément manquant (adresse, voisin, réseau) → un `set` l'ajoute ;
- élément en trop dans une zone gérée (autre adresse sur eth1, voisin ou réseau BGP non déclarés) → un `delete` le supprime.

Seul le delta est envoyé, dans un seul appel `/configure`, ce qui provoque un seul commit atomique côté VyOS, puis `save` via `/config-file`. Si l'état est déjà conforme, rien n'est envoyé : c'est l'idempotence.

## Remarques techniques
- Dans l'API réelle de VyOS, `commit` n'est pas une opération séparée : chaque appel `/configure` est commité automatiquement. Le script envoie donc tous les `set`/`delete` en un appel (= un commit) puis fait le `save`.
- Syntaxe BGP utilisée : VyOS 1.4+ (`protocols bgp system-as`). Sur VyOS 1.3 la syntaxe est `protocols bgp <AS> neighbor ...` : le script serait à adapter.
- `verify=False` est toléré en TP (certificat auto-signé) ; à éviter en production.
- La capture `show bgp summary` est à ajouter dans le rendu.

## Git
```bash
git add desired_state.yaml apply_state.py requirements.txt README.md
git commit -m "TP12: VyOS IaC - état désiré BGP et script déclaratif idempotent"
git push
```
