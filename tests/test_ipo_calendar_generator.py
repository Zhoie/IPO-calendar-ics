import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ipo_calendar_generator.py"


def load_generator_module():
    requests_module = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class ConnectionError(RequestException):
        pass

    class Timeout(RequestException):
        pass

    class HTTPError(RequestException):
        def __init__(self, message="", response=None):
            super().__init__(message)
            self.response = response

    requests_module.RequestException = RequestException
    requests_module.ConnectionError = ConnectionError
    requests_module.Timeout = Timeout
    requests_module.HTTPError = HTTPError

    dateutil_module = types.ModuleType("dateutil")
    tz_module = types.ModuleType("dateutil.tz")
    tz_module.gettz = lambda name: name
    dateutil_module.tz = tz_module

    ics_module = types.ModuleType("ics")

    class Calendar:
        def __init__(self):
            self.events = set()

        def __iter__(self):
            yield "BEGIN:VCALENDAR\n"
            yield "END:VCALENDAR\n"

    class Event:
        def __init__(self):
            self.name = ""
            self.begin = None
            self.description = ""
            self.location = ""

        def make_all_day(self):
            return None

    ics_module.Calendar = Calendar
    ics_module.Event = Event

    module_name = "ipo_calendar_generator_under_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)

    original_modules = {
        name: sys.modules.get(name)
        for name in ("requests", "dateutil", "dateutil.tz", "ics")
    }
    sys.modules["requests"] = requests_module
    sys.modules["dateutil"] = dateutil_module
    sys.modules["dateutil.tz"] = tz_module
    sys.modules["ics"] = ics_module

    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    return module


class FetchIPOsTests(unittest.TestCase):
    def test_fetch_ipos_retries_retryable_http_errors(self):
        module = load_generator_module()
        calls = []
        sleep_calls = []

        class Response:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self._payload = payload

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise module.requests.HTTPError(
                        f"HTTP {self.status_code}",
                        response=self,
                    )

            def json(self):
                return self._payload

        responses = iter(
            [
                Response(502, {}),
                Response(503, {}),
                Response(200, {"ipoCalendar": [{"symbol": "TEST"}]}),
            ]
        )

        session = types.SimpleNamespace(
            get=lambda *args, **kwargs: calls.append((args, kwargs)) or next(responses)
        )

        with mock.patch.dict(os.environ, {"FINNHUB_TOKEN": "test-token"}, clear=True):
            result = module.fetch_ipos(
                session=session,
                sleep_fn=lambda seconds: sleep_calls.append(seconds),
            )

        self.assertEqual(result, [{"symbol": "TEST"}])
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep_calls, [2, 4])

    def test_fetch_ipos_raises_non_retryable_http_errors(self):
        module = load_generator_module()

        class Response:
            status_code = 401

            def raise_for_status(self):
                raise module.requests.HTTPError("HTTP 401", response=self)

        session = types.SimpleNamespace(get=lambda *args, **kwargs: Response())

        with mock.patch.dict(os.environ, {"FINNHUB_TOKEN": "test-token"}, clear=True):
            with self.assertRaises(module.requests.HTTPError):
                module.fetch_ipos(session=session, sleep_fn=lambda seconds: None)


class MainTests(unittest.TestCase):
    def test_main_keeps_existing_calendar_when_upstream_is_down(self):
        module = load_generator_module()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "ipo_calendar.ics"
            output_file.write_text("existing calendar\n", encoding="utf-8")
            buffer = io.StringIO()

            with contextlib.redirect_stdout(buffer):
                module.main(
                    fetch_fn=lambda: (_ for _ in ()).throw(
                        module.RetryableFinnhubError("temporary outage")
                    ),
                    output_file=output_file,
                )

            self.assertEqual(
                output_file.read_text(encoding="utf-8"),
                "existing calendar\n",
            )
            self.assertIn("keeping existing calendar", buffer.getvalue())

    def test_main_raises_when_no_calendar_exists(self):
        module = load_generator_module()

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "ipo_calendar.ics"

            with self.assertRaises(module.RetryableFinnhubError):
                module.main(
                    fetch_fn=lambda: (_ for _ in ()).throw(
                        module.RetryableFinnhubError("temporary outage")
                    ),
                    output_file=output_file,
                )


if __name__ == "__main__":
    unittest.main()
