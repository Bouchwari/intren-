"""الإحصائيات المعمقة — monthly trends, absence patterns, document gaps.

The rules these hold, each of which would make the page lie if broken:
a month with no recorded days has no average; a rate with nothing behind it is
None rather than zero; completeness counts only days the school actually
served; and the trend counts EVERY meal type, Ramadan's included.
"""
import datetime
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import (
    MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA, MEAL_IFTAR, MEAL_SHOUR,
)
from core.analytics import (
    MonthPoint, absence_patterns, document_completeness, monthly_trend,
)
from core.models import (
    DailyAbsence, DailyContact, DailyReceptionRecord, DailyReport, OrderLetter,
    SchoolSettings,
)
from data import database


_PRICES = {MEAL_FTOUR: "3", MEAL_GHADA: "7", MEAL_ASHA: "4"}


class _AnalyticsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(SchoolSettings(
            school_name="مؤسسة", school_year="2025/2026", director="مدير",
            price_ftour="3", price_ghada="7", price_asha="4"))

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _contact(self, date: str, meal: str, count: int) -> None:
        database.save_daily_contact(DailyContact(
            date=date, meal_type=meal, collegial_granted=count))

    def _absence(self, date: str, meal: str, count: int,
                 cycle: str = "collegial_granted") -> None:
        database.save_daily_absence(DailyAbsence(
            date=date, meal_type=meal, **{cycle: count}))


class MonthlyTrendTests(_AnalyticsTestCase):
    def test_ramadan_meals_are_counted_in_the_month(self) -> None:
        """Regression: get_monthly_summaries hardcodes فطور/غداء/عشاء, so a
        month containing Ramadan came back missing everything served on its
        Ramadan days — the trend showed a collapse that never happened."""
        self._contact("2026-03-02", MEAL_GHADA, 100)
        self._contact("2026-03-03", MEAL_IFTAR, 80)
        self._contact("2026-03-03", MEAL_SHOUR, 70)

        point = monthly_trend(_PRICES)[0]
        self.assertEqual(point.month, "2026-03")
        self.assertEqual(point.meals, 250)

    def test_a_meal_with_no_price_is_counted_but_not_costed(self) -> None:
        """Ramadan pricing was deliberately dropped (2026-08-25), so those
        meals have no price. The month must say its cost is partial instead of
        printing a total that quietly understates it."""
        self._contact("2026-03-02", MEAL_GHADA, 100)
        self._contact("2026-03-03", MEAL_SHOUR, 70)

        point = monthly_trend(_PRICES)[0]
        self.assertEqual(point.cost, 700.0)          # 100 × 7, سحور excluded
        self.assertEqual(point.unpriced_meals, 70)
        self.assertTrue(point.cost_is_partial)

    def test_a_fully_priced_month_is_not_flagged(self) -> None:
        self._contact("2026-04-02", MEAL_GHADA, 10)
        point = monthly_trend(_PRICES)[0]
        self.assertFalse(point.cost_is_partial)

    def test_absence_is_netted_per_meal_not_on_the_month(self) -> None:
        """An absence booked against one meal must not cancel another meal's
        attendance — netting the aggregate would let it."""
        self._contact("2026-04-02", MEAL_GHADA, 100)
        self._absence("2026-04-02", MEAL_GHADA, 10)
        self._contact("2026-04-02", MEAL_FTOUR, 5)
        self._absence("2026-04-02", MEAL_FTOUR, 40)    # more absent than present

        point = monthly_trend(_PRICES)[0]
        self.assertEqual(point.meals, 90)   # 90 + max(0, 5-40), not 100-50=55

    def test_a_month_with_no_days_has_no_average(self) -> None:
        point = MonthPoint(month="2026-04", meals=0, days=0)
        self.assertIsNone(point.meals_per_day)

    def test_the_trend_reads_oldest_first(self) -> None:
        for month in ("2026-06", "2026-04", "2026-05"):
            self._contact(f"{month}-02", MEAL_GHADA, 10)
        self.assertEqual([point.month for point in monthly_trend(_PRICES)],
                         ["2026-04", "2026-05", "2026-06"])


class AbsencePatternTests(_AnalyticsTestCase):
    def test_a_rate_with_nothing_expected_is_none_not_zero(self) -> None:
        self._absence("2026-04-06", MEAL_GHADA, 5)     # absence, no contact
        patterns = absence_patterns("2026-04-01", "2026-04-30")
        self.assertEqual(patterns.total_absent, 5)
        self.assertIsNone(patterns.rate)

    def test_the_worst_weekday_is_the_highest_rate_not_the_biggest_count(self) -> None:
        """A weekday the school serves more often would otherwise always win
        on raw count alone."""
        # Monday: served twice, 10 absent out of 1000 → 1%
        for date in ("2026-04-06", "2026-04-13"):
            self._contact(date, MEAL_GHADA, 500)
            self._absence(date, MEAL_GHADA, 5)
        # Tuesday: served once, 8 absent out of 100 → 8%
        self._contact("2026-04-07", MEAL_GHADA, 100)
        self._absence("2026-04-07", MEAL_GHADA, 8)

        patterns = absence_patterns("2026-04-01", "2026-04-30")
        self.assertEqual(patterns.by_weekday[0], 10)      # Monday has more
        self.assertEqual(patterns.by_weekday[1], 8)
        self.assertEqual(patterns.worst_weekday, 1)       # …but Tuesday is worse

    def test_cycles_with_no_absence_are_left_out(self) -> None:
        self._contact("2026-04-06", MEAL_GHADA, 100)
        self._absence("2026-04-06", MEAL_GHADA, 4, cycle="qualifying_granted")
        patterns = absence_patterns("2026-04-01", "2026-04-30")
        self.assertEqual(patterns.by_cycle, {"qualifying": 4})


class CompletenessTests(_AnalyticsTestCase):
    def _full_day(self, date: str) -> None:
        self._contact(date, MEAL_GHADA, 10)
        self._absence(date, MEAL_GHADA, 1)
        database.save_daily_report(DailyReport(date=date))
        database.save_daily_reception_record(
            DailyReceptionRecord(date=date, ghada_qty=10))
        database.save_order_letter(
            OrderLetter(letter_date=date, period_start=date, period_end=date), [])

    def test_only_days_the_school_served_are_counted(self) -> None:
        """A month has ~30 dates and ~20 served days. Counting weekends and
        holidays as missing paperwork would make the number meaningless."""
        self._full_day("2026-04-06")
        self._full_day("2026-04-07")
        summary = document_completeness("2026-04-01", "2026-04-30")
        self.assertEqual(summary.served_days, 2)
        self.assertEqual(summary.complete_days, 2)
        self.assertEqual(summary.rate, 1.0)
        self.assertEqual(summary.gaps, [])

    def test_a_missing_document_is_named_on_its_own_day(self) -> None:
        self._full_day("2026-04-06")
        self._contact("2026-04-07", MEAL_GHADA, 10)     # nothing else
        summary = document_completeness("2026-04-01", "2026-04-30")

        self.assertEqual(summary.served_days, 2)
        self.assertEqual(summary.complete_days, 1)
        self.assertEqual([gap.date for gap in summary.gaps], ["2026-04-07"])
        self.assertEqual(sorted(summary.gaps[0].missing),
                         ["absence", "order_letter", "reception", "report"])

    def test_an_order_letter_covers_every_day_of_its_range(self) -> None:
        """It is the one document matched by RANGE, not by date equality."""
        for date in ("2026-04-06", "2026-04-07", "2026-04-08"):
            self._contact(date, MEAL_GHADA, 10)
        database.save_order_letter(OrderLetter(
            letter_date="2026-04-06", period_start="2026-04-06",
            period_end="2026-04-08"), [])
        summary = document_completeness("2026-04-01", "2026-04-30")
        self.assertEqual(summary.per_document["order_letter"], 3)

    def test_an_empty_month_reports_nothing_rather_than_zero_percent(self) -> None:
        summary = document_completeness("2026-04-01", "2026-04-30")
        self.assertEqual(summary.served_days, 0)
        self.assertIsNone(summary.rate)


class DeepPanelTests(_AnalyticsTestCase):
    """The panel has to build against an empty database — every screen in this
    app must survive 'nothing entered yet'."""

    def test_the_panel_builds_with_no_data_at_all(self) -> None:
        from ui.dashboard_deep import DeepStatsPanel
        panel = DeepStatsPanel()
        self.addCleanup(panel.deleteLater)
        self.assertEqual(panel._month_combo.count(), 0)
        self.assertFalse(panel._month_combo.isEnabled())

    def test_the_panel_lists_the_months_that_have_data(self) -> None:
        from ui.dashboard_deep import DeepStatsPanel
        self._contact("2026-04-06", MEAL_GHADA, 10)
        self._contact("2026-05-06", MEAL_GHADA, 10)
        panel = DeepStatsPanel()
        self.addCleanup(panel.deleteLater)
        months = [panel._month_combo.itemData(i)
                  for i in range(panel._month_combo.count())]
        self.assertEqual(months, ["2026-05", "2026-04"])   # newest first


class DonutLegendTests(unittest.TestCase):
    """Regression: the legend was drawn below the widget's own bottom edge, so
    every label on all four dashboard donuts was invisible."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_every_legend_entry_fits_inside_the_widget(self) -> None:
        from PySide6.QtGui import QFont, QFontMetrics
        from ui.dashboard_screen import DonutWidget

        donut = DonutWidget([("ابتدائي", 20, "#111111"),
                             ("إعدادي", 50, "#222222"),
                             ("تأهيلي", 30, "#333333")])
        donut.resize(300, 200)
        rows = donut._legend_rows(QFontMetrics(QFont("Segoe UI", 8)), 292)
        self.assertTrue(rows)
        self.assertEqual(sum(len(row) for row in rows), 3)
        for row in rows:
            width = sum(entry[2] for entry in row)
            self.assertLessEqual(width, 292 + 10 * len(row))

    def test_a_donut_with_no_data_has_no_legend(self) -> None:
        from PySide6.QtGui import QFont, QFontMetrics
        from ui.dashboard_screen import DonutWidget

        donut = DonutWidget([("ابتدائي", 0, "#111111")])
        self.assertEqual(
            donut._legend_rows(QFontMetrics(QFont("Segoe UI", 8)), 292), [])


if __name__ == "__main__":
    unittest.main()


class WorkDayBannerTests(unittest.TestCase):
    """The school banner moved from الإحصائيات to الصفحة الرئيسية (2026-08-29).

    On the statistics page it always showed TODAY. Here the screen has a date
    picker, so a banner that stayed on today while the cards below described
    another day would simply be wrong.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(SchoolSettings(
            school_name="ثانوية الاختبار", school_year="2025/2026",
            director="مدير"))

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _screen(self):
        from ui.work_pipeline_screen import WorkPipelineScreen
        screen = WorkPipelineScreen(navigate_to=lambda _index: None)
        self.addCleanup(screen.deleteLater)
        return screen

    def test_the_banner_follows_the_date_being_worked_on(self) -> None:
        from PySide6.QtCore import QDate
        screen = self._screen()
        screen._date_edit.setDate(QDate(2026, 5, 13))
        self.assertIn("13", screen._banner_date.text())
        self.assertIn("ماي", screen._banner_date.text())

    def test_the_banner_carries_the_school_name(self) -> None:
        screen = self._screen()
        self.assertIn("ثانوية الاختبار", screen._banner_subtitle.text())

    def test_a_school_with_no_name_yet_still_renders(self) -> None:
        database.save_school_settings(SchoolSettings(
            school_name="", school_year="2025/2026", director="مدير"))
        screen = self._screen()
        self.assertTrue(screen._banner_subtitle.text().strip())

    def test_the_statistics_page_no_longer_carries_them(self) -> None:
        """The user asked for the banner and the وصول سريع row to leave
        الإحصائيات — that page is for the numbers now."""
        from ui import dashboard_screen
        self.assertFalse(hasattr(dashboard_screen, "_build_welcome_panel"))
        self.assertFalse(hasattr(dashboard_screen, "_build_quick_actions"))

    def test_every_quick_link_points_at_a_real_screen(self) -> None:
        """A quick link is a hardcoded stack index — exactly the drift that
        has caused three bugs in main_window already."""
        from ui import main_window as mw
        from ui.work_pipeline_screen import _QUICK_LINKS

        pages = {index for _icon, _label, index in mw._NAV_ITEMS}
        for _icon, label, index in _QUICK_LINKS:
            self.assertIn(index, pages, label)
        # …and it points at the page whose name it carries.
        by_index = {index: name for _icon, name, index in mw._NAV_ITEMS}
        for _icon, label, index in _QUICK_LINKS:
            self.assertEqual(by_index[index], label)


class StatisticsReportTests(unittest.TestCase):
    """تقرير الإحصائيات — the statistics page as a signed PDF."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        self._settings = SchoolSettings(
            school_name="ثانوية الاختبار", school_year="2025/2026",
            director="مدير", price_ftour="3", price_ghada="7", price_asha="4")
        database.save_school_settings(self._settings)
        self._today = datetime.date(2026, 4, 30)

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _write(self, month: str = "2026-04") -> Path:
        from ui.dashboard_export import write_statistics_report_pdf
        path = Path(self._tmpdir.name) / "report.pdf"
        write_statistics_report_pdf(path, self._settings, month, self._today)
        return path

    def test_a_month_with_no_data_still_produces_a_report(self) -> None:
        """Every screen in this app has to survive 'nothing entered yet', and
        an export that crashes on an empty month is worse than a thin one."""
        path = self._write()
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 0)

    def test_a_real_month_produces_a_report(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-04-06", meal_type=MEAL_GHADA, collegial_granted=100))
        database.save_daily_absence(DailyAbsence(
            date="2026-04-06", meal_type=MEAL_GHADA, collegial_granted=5))
        path = self._write()
        self.assertGreater(path.stat().st_size, 0)

    def test_the_report_is_written_even_with_no_roster(self) -> None:
        """The feedback section reads ages off the roster; with no pupils
        imported it must print nothing rather than take the export down."""
        database.save_daily_contact(DailyContact(
            date="2026-04-06", meal_type=MEAL_GHADA, collegial_granted=10))
        self.assertTrue(self._write().exists())

    def test_month_bounds_cover_the_whole_month_including_december(self) -> None:
        from ui.dashboard_export import month_bounds
        self.assertEqual(month_bounds("2026-04"), ("2026-04-01", "2026-04-30"))
        self.assertEqual(month_bounds("2026-02"), ("2026-02-01", "2026-02-28"))
        # December has to roll the YEAR over, not just the month.
        self.assertEqual(month_bounds("2026-12"), ("2026-12-01", "2026-12-31"))


class WorkDayLayoutTests(unittest.TestCase):
    """Regression: the banner and the quick-access grid pushed الصفحة الرئيسية past
    the window height, and the QVBoxLayout crushed all five document cards to
    ~25px with their title, status and buttons drawn on top of each other."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(SchoolSettings(
            school_name="مؤسسة", school_year="2025/2026", director="مدير"))

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_no_card_is_crushed_at_the_smallest_window(self) -> None:
        from config.settings import WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH
        from ui import main_window as mw
        from ui.work_pipeline_screen import _PipelineCard

        window = mw.MainWindow()
        self.addCleanup(window.close)
        window.resize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        window.show()
        window._navigate(0)
        self.app.processEvents()

        cards = window._stack.widget(0).findChildren(_PipelineCard)
        self.assertEqual(len(cards), 5)
        crushed = [card.height() for card in cards
                   if card.height() < card.minimumHeight()]
        self.assertEqual(crushed, [])

    def test_a_card_declares_a_real_minimum_height(self) -> None:
        """With a minimum of zero the layout is free to squeeze it to nothing,
        which is exactly what happened."""
        from ui.work_pipeline_screen import _CARD_MIN_HEIGHT
        self.assertGreaterEqual(_CARD_MIN_HEIGHT, 50)


class ClassBreakdownTests(unittest.TestCase):
    """التلاميذ حسب القسم — every class with its own gender split."""

    def _pupil(self, name: str, student_class: str, gender: str,
               cycle: str = "إعدادي"):
        from core.models import Student
        return Student(full_name=name, student_class=student_class,
                       gender=gender, cycle=cycle)

    def test_classes_are_split_by_gender(self) -> None:
        from core.student_stats import breakdown_by_class
        rows = breakdown_by_class([
            self._pupil("أ", "الأولى إعدادي", "male"),
            self._pupil("ب", "الأولى إعدادي", "male"),
            self._pupil("ج", "الأولى إعدادي", "female"),
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].count("male"), 2)
        self.assertEqual(rows[0].count("female"), 1)
        self.assertEqual(rows[0].total, 3)

    def test_an_unrecorded_gender_is_counted_not_assigned(self) -> None:
        """It belongs to neither column — reported as its own number."""
        from core.student_stats import breakdown_by_class
        rows = breakdown_by_class([
            self._pupil("أ", "الأولى إعدادي", "male"),
            self._pupil("ب", "الأولى إعدادي", ""),
        ])
        self.assertEqual(rows[0].count("male"), 1)
        self.assertEqual(rows[0].count("female"), 0)
        self.assertEqual(rows[0].unknown_gender, 1)
        self.assertEqual(rows[0].total, 2)

    def test_classes_are_ordered_primary_then_collegial_then_qualifying(self) -> None:
        """Ordered through the app's own classifier, not by parsing "الأولى"
        out of a class name the school typed into Excel."""
        from core.student_stats import breakdown_by_class
        rows = breakdown_by_class([
            self._pupil("أ", "الجذع المشترك", "male", cycle="تأهيلي"),
            self._pupil("ب", "السادس ابتدائي", "male", cycle="ابتدائي"),
            self._pupil("ج", "الأولى إعدادي", "male", cycle="إعدادي"),
        ])
        self.assertEqual([row.name for row in rows],
                         ["السادس ابتدائي", "الأولى إعدادي", "الجذع المشترك"])

    def test_a_pupil_with_no_class_is_still_counted(self) -> None:
        from core.student_stats import breakdown_by_class
        rows = breakdown_by_class([self._pupil("أ", "", "male")])
        self.assertEqual(sum(row.total for row in rows), 1)

    def test_the_chart_rows_match_the_roster(self) -> None:
        from ui.dashboard_deep import class_chart_rows
        students = [self._pupil(f"ت{i}", "الأولى إعدادي", "male")
                    for i in range(5)]
        students += [self._pupil(f"ف{i}", "الثانية إعدادي", "female")
                     for i in range(3)]
        rows, totals = class_chart_rows(students)
        self.assertEqual(totals["all"], 8)
        self.assertEqual(totals["male"], 5)
        self.assertEqual(totals["female"], 3)
        # every bar's segments add up to the total printed beside it
        for _label, segments, total in rows:
            self.assertEqual(sum(value for value, _colour in segments), total)

    def test_a_bar_carries_a_segment_for_every_gender_present(self) -> None:
        """A class with no girls must still draw, with a zero-width segment
        rather than a missing one."""
        from ui.dashboard_deep import class_chart_rows
        rows, _totals = class_chart_rows(
            [self._pupil("أ", "الأولى إعدادي", "male")])
        _label, segments, total = rows[0]
        self.assertEqual(len(segments), 3)         # ذكور / إناث / غير محدد
        self.assertEqual(total, 1)
        self.assertEqual([value for value, _c in segments], [1, 0, 0])


class SidebarLabelTests(unittest.TestCase):
    """Two labels the user asked to change on 2026-08-29."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_the_landing_page_is_called_the_home_page(self) -> None:
        from ui import main_window as mw
        from ui.work_pipeline_screen import _TITLE
        labels = [label for _icon, label, _target in mw._NAV_TREE]
        self.assertIn("الصفحة الرئيسية", labels)
        self.assertNotIn("يوم العمل", labels)
        self.assertEqual(_TITLE, "الصفحة الرئيسية")

    def test_the_sidebar_title_carries_no_stray_letter(self) -> None:
        """It used to render as "M  <school name>"."""
        import tempfile as _tempfile
        tmpdir = _tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        original = database.DB_PATH
        database.DB_PATH = Path(tmpdir.name) / "test_matama.db"
        self.addCleanup(lambda: setattr(database, "DB_PATH", original))
        database.init_database()
        database.save_school_settings(SchoolSettings(
            school_name="ثانوية الاختبار", school_year="2025/2026",
            director="مدير"))

        from ui import main_window as mw
        window = mw.MainWindow()
        self.addCleanup(window.close)
        self.assertEqual(window._title_label.text(), "ثانوية الاختبار")
