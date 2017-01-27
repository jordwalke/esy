#!/usr/bin/env python

import re
import os
import json
import collections

import config

def generate_package_json(name, version, directory):
    opam_file = os.path.join(directory, 'opam')

    package_url = None
    version_file = os.path.join(directory, 'url')
    if os.path.exists(version_file):
        with open(version_file, 'r') as f:
            content = f.read()
            package_url = re.search(r"(archive:\s*|http:\s*|src:\s*)\"(.*)\"", content).group(2)

    def prefixWithScope(name):
        return "%s/%s" % (config.GH_ORG_NAME, name)

    def getVersionFromStr(str):
        g = re.search(r"([a-zA-Z0-9_\-]\.)?(\d+\.\d+\.\d+).*", str)
        if g:
            return g.group(2)

        g = re.search(r"([a-zA-Z0-9_\-]\.)?(\d+\.\d+).*", str)

        if g:
            return g.group(2) + ".0"

        g = re.search(r"([a-zA-Z0-9_\-]\.)?(\d+).*", str)
        if g:
            return g.group(2) + ".0.0"
        return "0.0.0"

    def getPrereleaseTag(name):
        g = re.search(r".*\+(.*)", name)

        if not g:
            return ""
        return "".join(re.findall(r"\d+", g.group(1)))

    def splitKV(txt):
        g = txt.split(":")
        return (g[0], ":".join(g[1:]).strip())

    def yieldKVPair(f):
        current = ""
        for l in open(f):
            if l.startswith("#"):
                continue
            l = l.split("#")[0]
            g = re.search(r"^([a-zA-Z\-]+)\s*:", l)
            if not g:
                current += l
            else:
                if current != "":
                    yield splitKV(current)
                current = l
        if current != "":
            yield splitKV(current)
    def unescapeTerm(term):
        if term.startswith("{"):
            return ""
        g = re.search(r'\"(.*)\"', term)
        if g:
            return term
        else:
            return builtInVars[term]

    def buildFlatList(txt):
        if txt.startswith("["):
            txt = txt[1:-1]
        txt = txt.strip()
        if txt == "":
            return []
        g = re.findall(r'\"(.*?)\"\s*(\{.*\})?', txt)
        return list(g)

    def breakList(txt):
        if txt.startswith("["):
            txt = txt[1:-1]
        txt = txt.strip()
        if txt == "":
            return []

        # Look for lists
        g = re.findall(r'\[([^\[\]]*)\]\s*\{?([^\{\}\[\]]*)\}?', txt, re.S)
        if not g:
            terms = [unescapeTerm(term) for term in re.split(r"[\s\n]+", txt)]

            return [(" ".join(terms), "")]
            # results = []
            # for line in re.split(r"\s+", txt):
            #     results.append((txt, ""))
                # g = re.search(r'"[a-zA-Z0-9\-]*"', line)
                # if not g:
                #     results.append((line, ""))
                #     continue
                # key = g.group(0)
                # g = re.search(r'\{(.*)\}', line)

                # if g:
                #     constraint = g.group(1)
                # else:
                #     constraint = ""
                # results.append((key, constraint))
            # return results
        return g

    def normalize_version_segment(version):
        version = re.sub(r'[^0-9]', '', version)
        if version == '':
            version = '0'
        return version

    def normalize_version(version):
        if '+' in version:
            [version, suffix] = version.split('+')
            suffix = re.sub(r'[^0-9]', '', suffix)
        else:
            suffix = ''
        parts = version.split('.', 2)
        if len(parts) == 1:
            (major,) = parts
            return '%s.0%s.0' % (normalize_version_segment(major), suffix)
        elif len(parts) == 2:
            (major, minor) = parts
            return '%s.%s%s.0' % (major, normalize_version_segment(minor), suffix)
        else:
            return version

    def cmdToStrings(cmd):
        return re.findall(r"\"[^\"]+\"|\S+", cmd)

    def unescapeBuiltinVariables(s):
        def escape(matched):
            var = matched.group(1)
            if var in builtInVars:
                return builtInVars[var]
            g = re.search(r"(.*):enable", var)
            if g:
                return "${%s_enable:-disable}" % g.group(1).replace("-", "_")
            g = re.search(r"(.*):installed", var)
            if g:
                return "${%s_installed:-false}" % g.group(1).replace("-", "_")
            raise Exception("Cannot expand variable %s" % var)
        return re.sub(r"%\{(.*?)\}%", escape, s)

    # TODO unhack this
    def filterCommands(filter):
        if filter == "ocaml-native":
            return False
        if filter == "!ocaml-native":
            return True
        if filter == "preinstalled":
            return True
        return False

    def createPostInstallCommand(substs, cmds):
        build = []

        for (subst, _) in substs:
            build.append("substs %s.in" % subst)

        for cmd in cmds:
            if filterCommands(cmd[1]):
                continue
            subCMDs = cmdToStrings(cmd[0])
            newCMDs = []
            for subCMD in subCMDs:
                g = re.search(r'\"(.*)\"', subCMD)
                if g:
                    newCMDs.append(g.group(1))
                else:
                    if not subCMD.startswith("{"):
                        newCMDs.append(builtInVars.get(subCMD, subCMD))
            build.append(" ".join(newCMDs))
    #       finalCMD += " && " + " ".join(newCMDs)
        build.append("(opam-installer --prefix=$cur__install || true)")
        return [unescapeBuiltinVariables(cmd) for cmd in build]

    def scoped(name):
        return '@%s/%s' % (config.NPM_SCOPE, name)

    def opamVersionToNpmVersion(v):
        v = v.group(0).strip("\"")
        return getVersionFromStr(v) + getPrereleaseTag(name)

    def opamRangeToNpmRange(range):
        if range == "" : return "*"
        range = range.strip("{}")
        assert ("|" not in range)
        ranges = [re.sub("\".*\"", opamVersionToNpmVersion, r) for r in [r.strip() for r in range.split("&")] if r != "build" and r != "test"]
        if len(ranges) == 0:
            return "*"
        return " ".join(ranges)

    d = collections.defaultdict(str)
    for (k, v) in yieldKVPair(opam_file):
        d[k] = v

    version = normalize_version(version)
    if name in config.OVERRIDE and 'version' in config.OVERRIDE[name]:
        version = config.OVERRIDE[name]['version'](version)

    builtInVars = {
        "name": name,
        "make": "make",
        "jobs": "4",
        "bin": "$cur__bin",
        "prefix": "$cur__install",
        "lib": "$cur__lib",
        "sbin": "$cur__sbin",
        "doc": "$cur__doc",
        "man": "$cur__man",
        "ocaml-native": "true",
        "ocaml-native-dynlink": "true",
        "pinned": "false",
    }


    packageJSON = {}
    packageJSON["name"] = scoped(name)
    packageJSON["version"] = version
    packageJSON["scripts"] = {}
    packageJSON["peerDependencies"] = {}
    packageJSON["esy"] = {}
    if name in config.OVERRIDE and 'build' in config.OVERRIDE[name]:
        packageJSON["esy"]["build"] = config.OVERRIDE[name]['build']
    else:
        packageJSON["esy"]["build"] = createPostInstallCommand(
            buildFlatList(d["substs"]), breakList(d["build"]) + breakList(d["install"]))
    packageJSON["dependencies"] = {
        "substs": "%s/substs" % (config.GH_ORG_NAME,),
        "opam-installer-bin": "andreypopp/opam-installer-bin",
    }

    for (dep, range) in buildFlatList(d["depends"]):
        if not config.is_dep_allowed(name, dep):
            continue
        if dep.startswith("base-"):
            continue
        dep = dep.strip("\" ")
        if dep == "":
            continue
        npm_range = opamRangeToNpmRange(range)
        packageJSON["dependencies"][scoped(dep)] = npm_range
    if name in config.ESY_EXTRA_DEP:
        for dep in config.ESY_EXTRA_DEP.get(name, {}):
            packageJSON["dependencies"][scoped(dep)] = '*'

    for (dep, range) in buildFlatList(d["depopts"]):
        dep = dep.strip("\" ")
        if not config.is_dep_allowed(name, dep):
            continue
        if dep == "" or dep in config.OPAM_DEPOPT_BLACKLIST:
            continue
        npm_range = opamRangeToNpmRange(range)
        packageJSON["dependencies"][scoped(dep)] = npm_range

    g = re.findall(r"ocaml-version ([!=<>]+.*?\".*?\")", d["available"])
    if g:
        g = " ".join(g)
        packageJSON["peerDependencies"]["ocaml"] = re.sub("\".*?\"", opamVersionToNpmVersion, g)
    else:
        packageJSON["peerDependencies"]["ocaml"] = ">= 4.2.3"

    packageJSON["opam"] = {'url': package_url}
    packageJSON["esy"]["buildsInSource"] = True
    packageJSON["esy"]["exportedEnv"] = {
        "%s_version" % name.replace("-", "_"): {
            "val": packageJSON["version"],
            "scope": "global"
        },
        "%s_enable" % name.replace("-", "_"): {
            "val": "enable",
            "scope": "global"
        },
        "%s_installed" % name.replace("-", "_"): {
            "val": "true",
            "scope": "global"
        },
    }

    if name in config.OVERRIDE and 'exportedEnv' in config.OVERRIDE[name]:
        packageJSON['esy']['exportedEnv'].update(config.OVERRIDE[name]['exportedEnv'])

    return packageJSON
