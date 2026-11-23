#!/usr/bin/env python3
"""TP 12 - VyOS : application dÃ©clarative d'un Ã©tat dÃ©sirÃ© (YAML) via l'API HTTP.

Principe : on lit l'Ã©tat actuel via /retrieve, on calcule le delta avec
desired_state.yaml, puis on envoie uniquement les set/delete nÃ©cessaires
(idempotence). Les valeurs gÃ©rÃ©es qui ne sont plus dans le YAML sont
supprimÃ©es (correction de dÃ©rive).

Syntaxe BGP : VyOS 1.4+ (protocols bgp system-as ...).
Pour VyOS 1.3 : adapter BGP_BASE / system-as (voir README).
"""
import argparse
import json
import os
import sys

import requests
import urllib3
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BGP_BASE = ["protocols", "bgp"]


class VyOS:
    def __init__(self, host, key):
        self.host = host
        self.key = key

    def _post(self, endpoint, payload):
        data = {"data": json.dumps(payload), "key": self.key}
        r = requests.post(f"https://{self.host}/{endpoint}", data=data,
                          verify=False, timeout=10)
        if r.status_code == 400 and endpoint == 'retrieve':
            return {"success": False, "data": None}
        r.raise_for_status()
        return r.json()

    # ---------- lecture de l'Ã©tat actuel ----------
    def get_value(self, path):
        b = self._post("retrieve", {"op": "returnValue", "path": path})
        return b["data"] if b.get("success") else None

    def get_values(self, path):
        b = self._post("retrieve", {"op": "returnValues", "path": path})
        return set(b["data"]) if b.get("success") and b["data"] else set()

    def get_children(self, path):
        b = self._post("retrieve", {"op": "showConfig", "path": path})
        if b.get("success") and isinstance(b.get("data"), dict):
            data = b["data"]
            leaf = path[-1]
            if set(data.keys()) == {leaf} and isinstance(data[leaf], dict):
                data = data[leaf]
            return set(data.keys())
        return set()

    def exists(self, path):
        b = self._post("retrieve", {"op": "exists", "path": path})
        return bool(b.get("success") and b.get("data"))

    # ---------- Ã©criture ----------
    def configure(self, commands):
        """Un seul appel = un seul commit atomique cÃ´tÃ© VyOS."""
        return self._post("configure", commands)

    def save(self):
        return self._post("config-file", {"op": "save"})


def as_list(x):
    return x if isinstance(x, list) else [x]


def plan(api, desired):
    """Retourne la liste des commandes set/delete Ã  envoyer (delta)."""
    cmds = []

    def set_leaf(path, value):
        if api.get_value(path) != str(value):
            cmds.append({"op": "set", "path": path, "value": str(value)})

    def set_node(path):
        if not api.exists(path):
            cmds.append({"op": "set", "path": path})

    # --- interfaces ---
    for name, cfg in (desired.get("interfaces") or {}).items():
        base = ["interfaces", "ethernet", name, "address"]
        want = set(as_list(cfg["address"]))
        have = api.get_values(base)
        for a in sorted(want - have):
            cmds.append({"op": "set", "path": base, "value": a})
        for a in sorted(have - want):  # dÃ©rive : adresse en trop
            cmds.append({"op": "delete", "path": base + [a]})

    # --- BGP ---
    bgp = desired.get("bgp")
    if bgp:
        set_leaf(BGP_BASE + ["system-as"], bgp["as_number"])

        nb_base = BGP_BASE + ["neighbor"]
        want_nb = {n["ip"]: n for n in bgp.get("neighbors", [])}
        for ip, n in want_nb.items():
            set_leaf(nb_base + [ip, "remote-as"], n["remote_as"])
            set_node(nb_base + [ip, "address-family", "ipv4-unicast"])
        for ip in sorted(api.get_children(nb_base) - set(want_nb)):
            cmds.append({"op": "delete", "path": nb_base + [ip]})

        net_base = BGP_BASE + ["address-family", "ipv4-unicast", "network"]
        want_net = set(bgp.get("networks", []))
        have_net = api.get_children(net_base)
        for net in sorted(want_net - have_net):
            cmds.append({"op": "set", "path": net_base + [net]})
        for net in sorted(have_net - want_net):
            cmds.append({"op": "delete", "path": net_base + [net]})

    return cmds


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default=os.getenv("VYOS_HOST", "192.168.1.1"))
    p.add_argument("--key", default=os.getenv("VYOS_KEY"))
    p.add_argument("--state", default="desired_state.yaml")
    p.add_argument("--dry-run", action="store_true",
                   help="affiche le delta sans rien appliquer")
    args = p.parse_args()

    if not args.key:
        sys.exit("ClÃ© API manquante : export VYOS_KEY=... ou --key")

    with open(args.state, encoding="utf-8") as f:
        desired = yaml.safe_load(f)

    api = VyOS(args.host, args.key)
    cmds = plan(api, desired)

    if not cmds:
        print("Aucun changement : l'Ã©tat actuel correspond Ã  l'Ã©tat dÃ©sirÃ©.")
        return

    print(f"{len(cmds)} modification(s) Ã  appliquer :")
    for c in cmds:
        print(" ", c["op"], "/".join(c["path"]), c.get("value", ""))

    if args.dry_run:
        print("(dry-run : rien n'a Ã©tÃ© envoyÃ©)")
        return

    res = api.configure(cmds)  # commit atomique
    if not res.get("success"):
        sys.exit(f"Erreur configure : {res.get('error')}")
    res = api.save()
    if not res.get("success"):
        sys.exit(f"Erreur save : {res.get('error')}")
    print("Configuration appliquÃ©e (commit) et sauvegardÃ©e (save).")


if __name__ == "__main__":
    main()


