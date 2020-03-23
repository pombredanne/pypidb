import unittest

from stdlib_list import stdlib_list

from pypidb._cache import get_file_cache, get_timeout
from pypidb._compat import PY2
from pypidb._db import Database, multipackage_repos
from pypidb._github import check_repo as check_github_repo
from pypidb._github import GitHubAPIMessage, get_repo_setuppy
from pypidb._pypi import IncompletePackageMetadata, InvalidPackage
from pypidb._similarity import _compute_similarity, normalize
from tests.data import mismatch, missing_repos, setuppy_mismatches, wrong_result

_stdlib_all = stdlib_list()
_stdlib = set(i.split(".")[0] for i in _stdlib_all)

USE_SEPARATE_INSTANCE = (
    True
)  # This can only be disabled if only one set of tests are run

web_session = get_file_cache("web")


def normalise_list(in_list):
    return [normalize(name) for name in in_list]


_global_converter = _global_db = Database(
    website_timeout=(15, 30), store_fetch_list=True
)


class _TestBase(unittest.TestCase):

    names = []

    expected_failures = ["sklearn", "bs4"]  # joejob/redirect  # "
    _run_expected_failures = True
    _ignore_invalid = False
    _allow_missing = False
    _debug_no_urls = False
    _allow_none = False
    _debug_multi_urls = False  # True

    def setUp(self):
        if USE_SEPARATE_INSTANCE:
            self.converter = Database(
                website_timeout=(15, 30), store_fetch_list=True
            )._converter
        else:
            self.converter = _global_converter

    def tearDown(self):
        pass

    def assertInsensitiveEqual(self, s, s2):
        if not s and self._allow_none:
            return

        self.assertIsNotNone(s)
        if isinstance(s2, str):
            if "/" in s2:
                self.assertEqual(s.lower(), s2.lower())
            else:
                self.assertIn("/" + s2.lower(), s.lower())
        else:
            self.assertIn(s.lower(), [i.lower() for i in s2])
            if self._debug_multi_urls:
                self.assertIsInstance(s2, str, "{} matches {!r}".format(s, s2))

    def assertRaisesNoUrls(self, name):
        try:
            url = self.converter.get_vcs(name)
        except IncompletePackageMetadata:
            if self._debug_no_urls:
                self.assertTrue(False)
            return
        self.assertIsNotNone(url)
        self.assertIsNone(url)

    def assertNoUrls(self, s):
        if self._debug_no_urls:
            self.assertIsNotNone(s)
        else:
            self.assertIsNone(s)

    def _test_names(self, names, ignore_not_found=False):
        assert len(names) == 1
        expected_failures = [normalize(i) for i in self.expected_failures]

        name = names[0]
        normalised_name = normalize(name)

        try:
            url = self.converter.get_vcs(name)
        except InvalidPackage:
            if (
                normalised_name in expected_failures
                or self._ignore_invalid
                or ignore_not_found
            ):
                return

            raise
        except IncompletePackageMetadata:
            if PY2:
                return
            if (
                normalised_name in expected_failures
                or self._ignore_invalid
                or self._allow_missing
                or ignore_not_found
            ):
                return

            raise
        except Exception:
            if PY2 or normalised_name in expected_failures:
                return

            raise

        if not url:
            if (
                normalised_name in expected_failures
                or self._allow_missing
                or ignore_not_found
            ):
                return

            assert False, name

        if normalised_name in missing_repos or normalised_name in expected_failures:
            return

        if name in wrong_result:
            return

        distance = _compute_similarity(name, url)

        if distance < 0.1:
            pass
        else:
            normalised_name = normalize(name)
            mismatch_urls = [
                value
                for key, value in mismatch.items()
                if normalize(key) == normalised_name
            ]
            if mismatch_urls:
                if (
                    url not in multipackage_repos
                    and url.lower() not in multipackage_repos
                ):
                    assert len(mismatch_urls) == 1, "{} matched {}".format(
                        name, mismatch_urls
                    )
                expected_url = mismatch_urls[0]
                self.assertInsensitiveEqual(url, expected_url)
            else:
                if name.startswith("azure"):
                    pass
                elif name.lower().startswith("xstatic-"):
                    pass
                else:
                    for rule in setuppy_mismatches:
                        if rule.endswith("-") and normalised_name.startswith(rule):
                            break
                    else:
                        raise Exception(
                            '"{}": "{}" should be in mismatches'.format(name, url)
                        )

        if url.startswith("https://github.com/"):

            slug = url[len("https://github.com/") :]
            try:
                rv = check_github_repo(slug)
            except Exception:
                rv = None
            if not rv:
                if PY2 or name in self.expected_failures:
                    return
                elif name in wrong_result:
                    return
                elif name.startswith("azure") or slug == "MicrosoftDocs/databricks-pr":
                    return
                assert False, slug

            for rule in setuppy_mismatches:
                rule = normalize(rule.strip("$"))
                if normalised_name.startswith(rule):
                    return

            try:
                rv = get_repo_setuppy(slug, normalised_name)
            except GitHubAPIMessage as e:
                raise unittest.SkipTest(str(e))

            if rv is not False:
                self.assertTrue(rv)

                if normalised_name not in normalize(rv):
                    assert False, "{} : {} not in \n{}".format(
                        name, normalised_name, rv
                    )

        else:
            r = web_session.get(url, timeout=get_timeout(url))
            r.raise_for_status()
