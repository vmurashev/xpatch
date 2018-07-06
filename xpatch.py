from __future__ import print_function
import sys
if sys.version_info[0] < 3:
    import ConfigParser as configparser
else:
    import configparser

import argparse
import os.path
import re

ABI_ALL=['x86', 'x86_64', 'arm', 'arm64', 'macosx']

TAG_INI_SECTION_ALL = 'all'
TAG_INI_ENABLED_FEATURES = 'ENABLED_FEATURES'
TAG_INI_DISABLED_FEATURES = 'DISABLED_FEATURES'
TAG_INI_DISCARDED_FEATURES = 'DISCARDED_FEATURES'
TAG_INI_XSTRINGS = 'XSTRINGS'
TAG_INI_PREFIX_XSTRING = 'XSTRING_'

RE_ONE_LINE_COMMENT = re.compile(r'\s*/\*(.*)\*/\s*')
RE_C_DEFINE = re.compile(r'\s*#\s*define\s+(\S+)\s+(.*)')
RE_C_UNDEF = re.compile(r'\s*#\s*undef\s+(\S+)')


def is_one_line_comment(line):
    m = re.match(RE_ONE_LINE_COMMENT, line)
    if m:
        return True
    return False


def strip_comment(line):
    m = re.match(RE_ONE_LINE_COMMENT, line)
    if m:
        commented_text = m.group(1)
        if commented_text is not None:
            return commented_text
    return line


def fetch_define(line):
    m = re.match(RE_C_DEFINE, line)
    if m:
        key, value = m.group(1,2)
        if key is not None and value is not None:
            if '*/' in value:
                return None, None
            return key, value
    return None, None


def fetch_undef(line):
    m = re.match(RE_C_UNDEF, line)
    if m:
        key = m.group(1)
        if key is not None:
            return key
    return None


def parse_feature_info(line, to_discard, xstrings):
    line = strip_comment(line)
    def_key, def_value = fetch_define(line)
    if def_key is not None:
        if def_key in to_discard:
            return def_key, None
        if def_key in xstrings:
            return def_key, def_value
    if def_value is not None:
        if def_value == '1':
            return def_key, True
        return def_key, None
    undef_key = fetch_undef(line)
    if undef_key is not None:
        if undef_key in to_discard:
            return undef_key, None
        return undef_key, False
    return None, None


class PatchConfig:
    def __init__(self, enabled_features, disabled_features, discarded_features, xstrings):
        self.enabled_features = enabled_features
        self.disabled_features = disabled_features
        self.discarded_features = discarded_features
        self.xstrings = xstrings

    def feature_to_discard(self, feature_name):
        if feature_name in self.discarded_features:
            return True
        return False

    def get_feature_status(self, feature_name):
        if feature_name in self.enabled_features:
            return True
        if feature_name in self.disabled_features:
            return False
        return None

def apply_patch(config, input_file, output_file):
    with open(input_file) as fh:
        input_lines = [ ln.rstrip('\r\n') for ln in fh.readlines() ]

    output_lines = []
    first = True
    for ln in input_lines:
        status_changed = False
        needed_status = None
        ln_replacemnent = None
        feature_name, feature_status = parse_feature_info(ln, config.discarded_features, config.xstrings)
        if feature_name is not None:
            if config.feature_to_discard(feature_name):
                prev_line = None
                if output_lines:
                    prev_line = output_lines[-1]
                    if is_one_line_comment(prev_line):
                        del output_lines[-1]
                        if output_lines and not output_lines[-1].strip():
                            del output_lines[-1]
                    else:
                        prev_line = None
                if not first:
                    print("    |")
                if prev_line is not None:
                    print("<<< |{}|".format(prev_line))
                print("<<< |{}|".format(ln))
                continue

            if feature_name in config.xstrings:
                if feature_status == config.xstrings[feature_name]:
                    output_lines.append(ln)
                    continue
                ln_replacemnent = '#define {} {}'.format(feature_name, config.xstrings[feature_name])

            needed_status = config.get_feature_status(feature_name)
            if needed_status is not None and feature_status is not None:
                if needed_status != feature_status:
                    status_changed = True

        if ln_replacemnent is None and needed_status is True and status_changed:
            ln_replacemnent = '#define {} 1'.format(feature_name)

        if ln_replacemnent is None and needed_status is False and feature_name is not None and feature_status is None:
            ln_replacemnent = '/* #undef {} */'.format(feature_name)

        if ln_replacemnent is None and needed_status is False and status_changed:
            ln_replacemnent = '/* #undef {} */'.format(feature_name)

        if ln_replacemnent is not None:
            if not first:
                print("    |")
            print("<<< |{}|".format(ln))
            print(">>> |{}|".format(ln_replacemnent))
            output_lines.append(ln_replacemnent)
            first = False
        else:
            output_lines.append(ln)

    with open(output_file, mode='wb') as fh:
        for ln in output_lines:
            fh.writelines([ln.encode('ascii'), b'\n'])


def load_ini_config(path):
    with open(path):
        pass
    config = configparser.RawConfigParser()
    config.optionxform=str
    config.read(path)
    return config


def get_ini_conf_strings(config, section, option):
    return config.get(section, option).split()


def get_ini_conf_string1(config, section, option):
    return config.get(section, option).strip()

def get_ini_conf_strings_optional(config, section, option):
    if not config.has_option(section, option):
        return []
    return get_ini_conf_strings(config, section, option)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--abi', nargs=1, choices=ABI_ALL, required=True)
    parser.add_argument('--config', nargs=1, type=str, required=True)
    parser.add_argument('--input', nargs=1, type=str, required=True)
    parser.add_argument('--output', nargs=1, type=str, required=True)
    args = parser.parse_args()

    abi = args.abi[0]
    input_file = os.path.normpath(os.path.abspath(args.input[0]))
    output_file = os.path.normpath(os.path.abspath(args.output[0]))
    config_file = os.path.normpath(os.path.abspath(args.config[0]))

    ini_conf = load_ini_config(config_file)

    enabled_features = get_ini_conf_strings_optional(ini_conf, TAG_INI_SECTION_ALL, TAG_INI_ENABLED_FEATURES)
    enabled_features.extend(get_ini_conf_strings_optional(ini_conf, abi, TAG_INI_ENABLED_FEATURES))

    disabled_features = get_ini_conf_strings_optional(ini_conf, TAG_INI_SECTION_ALL, TAG_INI_DISABLED_FEATURES)
    disabled_features.extend(get_ini_conf_strings_optional(ini_conf, abi, TAG_INI_DISABLED_FEATURES))

    discarded_features = get_ini_conf_strings_optional(ini_conf, TAG_INI_SECTION_ALL, TAG_INI_DISCARDED_FEATURES)
    discarded_features.extend(get_ini_conf_strings_optional(ini_conf, abi, TAG_INI_DISCARDED_FEATURES))

    xstrings_names = get_ini_conf_strings_optional(ini_conf, TAG_INI_SECTION_ALL, TAG_INI_XSTRINGS)
    xstrings_names_abi = get_ini_conf_strings_optional(ini_conf, abi, TAG_INI_XSTRINGS)

    xstrings = {}
    for xn in xstrings_names:
        xvalue = get_ini_conf_string1(ini_conf, TAG_INI_SECTION_ALL, TAG_INI_PREFIX_XSTRING + xn)
        xstrings[xn] = xvalue
    for xn in xstrings_names_abi:
        xvalue = get_ini_conf_string1(ini_conf, abi, TAG_INI_PREFIX_XSTRING + xn)
        xstrings[xn] = xvalue

    config = PatchConfig(enabled_features, disabled_features, discarded_features, xstrings)
    print('[{}] {}'.format(abi, 32*'-'))
    apply_patch(config, input_file, output_file)
    print('[{}] {}'.format(abi, 32*'-'))
    print("Input file: '{}'".format(input_file))
    print("Generated file: '{}'".format(output_file))
