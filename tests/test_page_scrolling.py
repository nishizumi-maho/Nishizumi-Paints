import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_scroll_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class PreferredWindowSizeTests(unittest.TestCase):
    def test_large_screen_keeps_the_preferred_size(self):
        self.assertEqual(APP.preferred_window_size(2560, 1440), APP.WINDOW_PREFERRED_SIZE)

    def test_laptop_screen_is_not_exceeded(self):
        width, height = APP.preferred_window_size(1366, 768)
        self.assertEqual((width, height), (1326, 688))
        self.assertLessEqual(width, 1366)
        self.assertLessEqual(height, 768)

    def test_tiny_screen_still_gets_a_usable_window(self):
        self.assertEqual(APP.preferred_window_size(320, 240), APP.WINDOW_ABSOLUTE_MIN_SIZE)

    def test_unusable_screen_metrics_fall_back_to_the_preferred_size(self):
        self.assertEqual(APP.preferred_window_size("", None), APP.WINDOW_PREFERRED_SIZE)

    def test_minimum_window_never_exceeds_the_screen(self):
        width, height = APP.preferred_window_size(800, 600)
        self.assertLessEqual(min(APP.WINDOW_MIN_SIZE[0], width), width)
        self.assertLessEqual(min(APP.WINDOW_MIN_SIZE[1], height), height)


class ScrollablePageGeometryTests(unittest.TestCase):
    def test_content_that_fits_fills_the_view_without_scrollbars(self):
        width, height, needs_horizontal, needs_vertical = APP.scrollable_page_geometry(900, 600, 700, 480)
        self.assertEqual((width, height), (900, 600))
        self.assertFalse(needs_horizontal)
        self.assertFalse(needs_vertical)

    def test_tall_content_keeps_its_height_and_asks_for_a_vertical_bar(self):
        width, height, needs_horizontal, needs_vertical = APP.scrollable_page_geometry(900, 600, 700, 1200)
        self.assertEqual((width, height), (900, 1200))
        self.assertFalse(needs_horizontal)
        self.assertTrue(needs_vertical)

    def test_wide_content_keeps_its_width_and_asks_for_a_horizontal_bar(self):
        width, height, needs_horizontal, needs_vertical = APP.scrollable_page_geometry(900, 600, 1400, 480)
        self.assertEqual((width, height), (1400, 600))
        self.assertTrue(needs_horizontal)
        self.assertFalse(needs_vertical)

    def test_exact_fit_does_not_add_scrollbars(self):
        self.assertEqual(APP.scrollable_page_geometry(900, 600, 900, 600), (900, 600, False, False))

    def test_one_pixel_of_rounding_does_not_add_scrollbars(self):
        self.assertEqual(APP.scrollable_page_geometry(900, 600, 901, 601)[2:], (False, False))
        self.assertEqual(APP.scrollable_page_geometry(900, 600, 902, 602)[2:], (True, True))

    def test_unmapped_sizes_are_treated_as_one_pixel(self):
        self.assertEqual(APP.scrollable_page_geometry(0, -5, "", None), (1, 1, False, False))


class MousewheelScrollStepsTests(unittest.TestCase):
    def test_windows_notch_down_scrolls_one_unit_down(self):
        self.assertEqual(APP.mousewheel_scroll_steps(-120), 1)

    def test_windows_notch_up_scrolls_one_unit_up(self):
        self.assertEqual(APP.mousewheel_scroll_steps(120), -1)

    def test_fast_wheel_scrolls_proportionally(self):
        self.assertEqual(APP.mousewheel_scroll_steps(-360), 3)
        self.assertEqual(APP.mousewheel_scroll_steps(240), -2)

    def test_precision_wheels_scroll_one_unit(self):
        self.assertEqual(APP.mousewheel_scroll_steps(-3), 1)
        self.assertEqual(APP.mousewheel_scroll_steps(7), -1)

    def test_x11_wheel_buttons_are_understood(self):
        self.assertEqual(APP.mousewheel_scroll_steps(0, 4), -1)
        self.assertEqual(APP.mousewheel_scroll_steps(0, 5), 1)

    def test_events_without_movement_are_ignored(self):
        self.assertEqual(APP.mousewheel_scroll_steps(0), 0)
        self.assertEqual(APP.mousewheel_scroll_steps(None), 0)
        self.assertEqual(APP.mousewheel_scroll_steps("", ""), 0)


class _WheelEvent:
    def __init__(self, delta=-120, num=0):
        self.delta = delta
        self.num = num
        self.x_root = 0
        self.y_root = 0


class ScrollablePageWidgetTests(unittest.TestCase):
    """Exercise the real Tk widgets a scrollable tab is made of."""

    def setUp(self):
        try:
            import tkinter
            from tkinter import ttk
        except ImportError as exc:  # pragma: no cover - depends on the Python build
            raise unittest.SkipTest(f"tkinter is not available: {exc}")
        try:
            self.root = tkinter.Tk()
        except tkinter.TclError as exc:  # pragma: no cover - depends on the display
            raise unittest.SkipTest(f"no display available for Tk: {exc}")
        self.tkinter = tkinter
        self.ttk = ttk
        self.root.geometry("500x300")
        self.ui = APP.DownloaderUI.__new__(APP.DownloaderUI)
        self.ui.tk = tkinter
        self.ui.ttk = ttk
        self.ui.root = self.root
        self.ui._page_scroll_states = {}
        self.ui._bind_page_scroll_events()
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)
        self.tab, self.page = self.ui._add_scrollable_tab(self.notebook, "Options")
        self.state = self.ui._page_scroll_states[str(self.page.master)]
        self.canvas = self.state["canvas"]
        self.page.columnconfigure(0, weight=1)
        self._settle()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def _settle(self, rounds: int = 6):
        for _ in range(rounds):
            self.root.update()

    def _refresh(self):
        self._settle()
        self.ui._refresh_page_scroll_regions()
        self._settle()

    def _add_options(self, count: int, first_row: int = 0):
        widgets = []
        for index in range(count):
            widget = self.ttk.Label(self.page, text=f"option {index}")
            widget.grid(row=first_row + index, column=0, sticky="w")
            widgets.append(widget)
        return widgets

    def test_page_that_fits_fills_the_view_and_shows_no_scrollbar(self):
        self.ttk.Label(self.page, text="only option").grid(row=0, column=0, sticky="w")
        self._refresh()
        self.assertFalse(self.state["vertical_shown"])
        self.assertFalse(self.state["vertical_bar"].winfo_ismapped())
        self.assertEqual(self.page.winfo_height(), self.canvas.winfo_height())
        self.assertEqual(self.page.winfo_width(), self.canvas.winfo_width())

    def test_options_below_the_window_stay_reachable(self):
        options = self._add_options(60)
        self._refresh()
        self.assertTrue(self.state["vertical_shown"])
        self.assertTrue(self.state["vertical_bar"].winfo_ismapped())
        last = options[-1]
        self.assertGreater(
            last.winfo_rooty() + last.winfo_height(),
            self.canvas.winfo_rooty() + self.canvas.winfo_height(),
        )
        self.canvas.yview_moveto(1.0)
        self._settle()
        self.assertLessEqual(
            last.winfo_rooty() + last.winfo_height(),
            self.canvas.winfo_rooty() + self.canvas.winfo_height(),
        )

    def test_content_that_appears_later_updates_the_scrollbar(self):
        self.ttk.Label(self.page, text="only option").grid(row=0, column=0, sticky="w")
        self._refresh()
        self.assertFalse(self.state["vertical_shown"])
        extra = self._add_options(40, first_row=1)
        self._refresh()
        self.assertTrue(self.state["vertical_shown"])
        for widget in extra:
            widget.destroy()
        self._refresh()
        self.assertFalse(self.state["vertical_shown"])
        self.assertEqual(self.canvas.yview(), (0.0, 1.0))

    def test_wheel_scrolls_the_page_under_the_pointer(self):
        self._add_options(60)
        self._refresh()
        self.root.winfo_containing = lambda _x, _y: self.page
        self.assertEqual(self.ui._on_page_mousewheel(_WheelEvent(delta=-120)), "break")
        self._settle()
        self.assertGreater(self.canvas.yview()[0], 0.0)

    def test_wheel_does_nothing_on_a_page_that_fits(self):
        self.ttk.Label(self.page, text="only option").grid(row=0, column=0, sticky="w")
        self._refresh()
        self.root.winfo_containing = lambda _x, _y: self.page
        self.assertIsNone(self.ui._on_page_mousewheel(_WheelEvent(delta=-120)))
        self.assertEqual(self.canvas.yview(), (0.0, 1.0))

    def test_wheel_over_a_scrolling_list_leaves_the_page_alone(self):
        listbox = self.tkinter.Listbox(self.page, height=4)
        listbox.grid(row=0, column=0, sticky="ew")
        for index in range(50):
            listbox.insert("end", f"paint {index}")
        self._add_options(60, first_row=1)
        self._refresh()
        self.assertTrue(self.state["vertical_shown"])
        self.assertTrue(self.ui._widget_scrolls_itself(listbox, "y"))
        self.root.winfo_containing = lambda _x, _y: listbox
        self.ui._on_page_mousewheel(_WheelEvent(delta=-120))
        self._settle()
        self.assertEqual(self.canvas.yview()[0], 0.0)

    def test_a_list_that_shows_everything_lets_the_page_scroll(self):
        listbox = self.tkinter.Listbox(self.page, height=4)
        listbox.grid(row=0, column=0, sticky="ew")
        listbox.insert("end", "the only paint")
        self._add_options(60, first_row=1)
        self._refresh()
        self.assertFalse(self.ui._widget_scrolls_itself(listbox, "y"))
        self.root.winfo_containing = lambda _x, _y: listbox
        self.assertEqual(self.ui._on_page_mousewheel(_WheelEvent(delta=-120)), "break")
        self._settle()
        self.assertGreater(self.canvas.yview()[0], 0.0)

    def test_hidden_tabs_are_measured_once_they_are_shown(self):
        hidden_tab, hidden_page = self.ui._add_scrollable_tab(self.notebook, "Hidden")
        hidden_state = self.ui._page_scroll_states[str(hidden_page.master)]
        for index in range(60):
            self.ttk.Label(hidden_page, text=f"hidden option {index}").grid(row=index, column=0, sticky="w")
        self._refresh()
        self.assertFalse(hidden_state["vertical_shown"])
        self.notebook.select(hidden_tab)
        self._refresh()
        self.assertTrue(hidden_state["vertical_shown"])


if __name__ == "__main__":
    unittest.main()
