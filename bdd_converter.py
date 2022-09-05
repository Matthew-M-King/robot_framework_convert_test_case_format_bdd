#!/usr/bin/env python

import os.path
import sys
import time


from robot.conf import RobotSettings
from robot.running import TestSuiteBuilder
from robot.utils import (abspath, Application, file_writer, get_link_path,
                        is_string, secs_to_timestr, seq2str2, timestr_to_secs, unescape)

USAGE = """robot.bdd_converter -- Robot Framework robot to feature file converter"""



def TestSuiteFactory(datasources, **options):
    settings = RobotSettings(options)
    if is_string(datasources):
        datasources = [datasources]
    suite = TestSuiteBuilder(process_curdir=False).build(*datasources)
    suite.configure(**settings.suite_config)
    return suite



class BDDConverter(Application):
    def __init__(self):
        Application.__init__(self, USAGE, arg_limits=(2,))

    def main(self, datasources, title=None, **options):
        outdir = abspath(datasources.pop())
        suite = TestSuiteFactory(datasources, **options)
        self._write_bdd(suite, outdir, title)
        self.console(outdir)

    def _write_bdd(self, suite, outdir, title):
        models = FeatureWriter(outdir, suite, title).convert_data()


class FeatureWriter:

    def __init__(self, output, suite, title=None):
        self._output = output
        self._suite = suite
        self._title = title.replace('_', ' ') if title else suite.name

    def convert_data(self):
        return dict(
            suite=Builder(self._output)._build_suite(self._suite),
            title=self._title,
            generated=int(time.time() * 1000)
        )
        

class Builder:

    def __init__(self, output_path=None):
        self._output_path = output_path

    def _build_suite(self, suite):
        return dict(
            source=suite.source or '',
            relativeSource=self._get_relative_source(suite.source),
            id=suite.id,
            name=suite.name,
            fullName=suite.longname,
            doc=suite.doc,
            numberOfTests=suite.test_count,
            suites=self._build_suites(suite),
            tests=self._write_tests(suite),
            keywords=list(self._build_keywords((suite.setup, suite.teardown)))
        )

    def _get_relative_source(self, source):
        if not source or not self._output_path:
            return ''
        return get_link_path(source, os.path.dirname(self._output_path))

    def _build_suites(self, suite):
        return [self._build_suite(s) for s in suite.suites]


    def _write_tests(self, suite):
        if suite.tests:
            tests = [self._build_test(t) for t in suite.tests]
            filename = suite.name.replace(' ', '_')
            filename += '.feature'
            
            with file_writer(filename, usage='Feature output') as feature:
                feature.write('Feature: ' + suite.name + '\n\n\n')
                for test in tests:
                    print(test)
                    feature.write('t' + test['tags'])
                    feature.write('\t' + test['name'] + '\n')
                    for keyword in test['keywords']:
                        feature.write('\t\t' + keyword['name'] + keyword['arguments'] + '\n')
                    feature.write('\n')
            
            
    def _build_test(self, test):
        if test.setup:
            test.body.insert(0, test.setup)
        if test.teardown:
            test.body.append(test.teardown)

        if 'scenario' not in str(test.name).lower():
            test_name = 'Scenario: ' + test.name
        else:
            test_name = test.name

        return dict(
            name=test_name,
            fullName=test.longname,
            id=test.id,
            doc=test.doc,
            tags=[t for t in test.tags],
            timeout=self._get_timeout(test.timeout),
            keywords=list(self._build_keywords(test.body))
        )

    def _build_keywords(self, keywords):
        for kw in keywords:
            if not kw:
                continue
            if kw.type == kw.SETUP:
                yield self._build_keyword(kw, 'SETUP')
            elif kw.type == kw.TEARDOWN:
                yield self._build_keyword(kw, 'TEARDOWN')
            elif kw.type == kw.FOR:
                yield self._build_for(kw)
            elif kw.type == kw.WHILE:
                yield self._build_while(kw)
            elif kw.type == kw.IF_ELSE_ROOT:
                yield from self._build_if(kw)
            elif kw.type == kw.TRY_EXCEPT_ROOT:
                yield from self._build_try(kw)
            else:
                yield self._build_keyword(kw, 'KEYWORD')

    def _build_for(self, data):
        name = '%s %s %s' % (', '.join(data.variables), data.flavor,
                             seq2str2(data.values))
        return {'type': 'FOR', 'name': name, 'arguments': ''}

    def _build_while(self, data):
        return {'type': 'WHILE', 'name': data.condition, 'arguments': ''}

    def _build_if(self, data):
        for branch in data.body:
            yield {'type': branch.type,
                   'name': branch.condition or '',
                   'arguments': ''}

    def _build_try(self, data):
        for branch in data.body:
            if branch.type == branch.EXCEPT:
                patterns = ', '.join(branch.patterns)
                as_var = f'AS {branch.variable}' if branch.variable else ''
                name = f'{patterns} {as_var}'.strip()
            else:
                name = ''
            yield {'type': branch.type, 'name': name, 'arguments': ''}

    def _build_keyword(self, kw, kw_type):
        
        # Check for data table
        if self._get_kw_name(kw) == '^' or self._get_kw_name(kw) == '>':
            name = ''
            args = self._build_data_row(kw.args)
        else:
            name = self._get_kw_name(kw)
            args = ', '.join(kw.args)
        
        return {
            'type': kw_type,
            'name': name,
            'arguments': args
        }

    def _build_data_row(self, row_data):
        row_data = ' | '.join(row_data)
        row_data = '\t| ' + row_data + ' |'
        return row_data

    def _get_kw_name(self, kw):
        if kw.assign:
            return '%s = %s' % (', '.join(a.rstrip('= ') for a in kw.assign), kw.name)
        return kw.name

    def _get_timeout(self, timeout):
        if timeout is None:
            return ''
        try:
            tout = secs_to_timestr(timestr_to_secs(timeout))
        except ValueError:
            tout = timeout
        return tout
        

def bdd_converter_cli(arguments):
    BDDConverter().execute_cli(arguments)

def bdd_converter(*arguments, **options):
    """Executes `BDDConverter` programmatically.

    Arguments and options have same semantics, and options have same names,
    as arguments and options to BDDConverter."""

    BDDConverter().execute(*arguments, **options)


if __name__ == '__main__':
    bdd_converter_cli(sys.argv[1:])