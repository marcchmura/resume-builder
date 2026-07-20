"""
resume_engine.py
----------------
Millimetre-accurate PDF renderer replicating the original Word resume
(CV-corpo.docx). Every constant below was measured (in PDF points,
1 pt = 0.3528 mm) directly from the reference PDF export of the Word file.

Fonts: base-14 Times (Roman/Bold/Italic/BoldItalic) -- metrically
compatible with Times New Roman, so line widths match Word exactly.
"""

import io
from copy import deepcopy

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = letter  # 612 x 792 pt (US Letter, as in the Word file)

# ---------------------------------------------------------------------------
# GEOMETRY -- all values in points, measured from the reference resume.
# "top" values are distances from the TOP of the page to the TOP of the glyphs
# (same convention as Word). The engine converts to baselines internally.
# ---------------------------------------------------------------------------
CONFIG = {
    # ---- page frame -------------------------------------------------------
    "rule_x0": 34.5,           # section rule: left end
    "rule_x1": 579.4,          # section rule: right end
    "rule_width": 0.5,         # rule thickness
    "bottom_limit": 780.0,     # max allowed "top" before page overflow

    # ---- header (name / contact / city) -----------------------------------
    "name_top": 34.1,
    "name_size": 14,
    "contact_top": 52.0,
    "contact_size": 10,
    "city_top": 65.4,
    # gap: bottom of header block -> first section rule
    "header_to_first_rule": 24.05,   # city_top(65.4) -> rule(89.45)

    # ---- section skeleton --------------------------------------------------
    "rule_to_title": 3.65,     # rule y -> section title top
    "title_size": 10,
    "title_x": 40.0,
    # gap: section title top -> first content line top  (per section type)
    "title_to_content": {
        "experience": 14.5,
        "education": 15.5,
        "kv": 15.2,
        "bullets": 15.5,
        "projects": 14.5,
        "summary": 15.0,
    },
    # gap: last content line top -> NEXT section rule
    "section_gap": 25.0,

    # ---- columns -----------------------------------------------------------
    "date_x": 40.0,            # dates / duration / small note column
    "col2_x": 116.5,           # company, role, degree, detail lines
    "right_x": 576.0,          # right-aligned location edge
    "body_size": 10,

    # ---- experience entries ------------------------------------------------
    "exp_header_to_role": 11.6,   # company line -> role line
    "exp_role_to_bullet": 13.0,   # role line -> first bullet
    "exp_bullet_step": 14.0,      # bullet -> next bullet
    "exp_wrap_step": 12.5,        # wrapped continuation line
    "exp_entry_gap": 19.7,        # last line of entry -> next entry header
    "bullet_dot_x": 117.8,        # centre of the bullet dot
    "bullet_text_x": 122.5,
    "bullet_radius": 1.55,

    # ---- project entries ----------------------------------------------------
    "proj_header_to_bullet": 13.0,  # name/date line -> first bullet
    "proj_bullet_step": 14.0,       # bullet -> next bullet
    "proj_wrap_step": 12.5,         # wrapped continuation line
    "proj_entry_gap": 19.7,         # last line of entry -> next entry header

    # ---- education entries ---------------------------------------------------
    "edu_line_step": 11.6,        # school header -> degree, and between lines
    "edu_entry_gap": 17.5,        # last line -> next school header
    "edu_note_size": 6.5,         # "Expected grad. Jan 27"

    # ---- key/value section (skills) -----------------------------------------
    "kv_label_x": 41.5,
    "kv_content_x": 121.05,
    "kv_row_step": 11.5,

    # ---- bold-lead bullet section (activities) ------------------------------
    "act_dot_x": 119.4,
    "act_text_x": 124.0,
    "act_step": 12.2,

    # ---- summary (plain paragraph) -------------------------------------------
    "summary_line_step": 12.5,
}

ASCENT = 0.683  # Times ascent fraction (top of glyphs -> baseline)

F_REG, F_BOLD, F_ITAL, F_BI = ("Times-Roman", "Times-Bold",
                               "Times-Italic", "Times-BoldItalic")


def _wrap(text, font, size, first_w, rest_w):
    """Greedy word wrap. Returns list of lines (first line fits first_w)."""
    words, lines, cur, limit = text.split(), [], "", first_w
    for w in words:
        trial = (cur + " " + w).strip()
        if stringWidth(trial, font, size) <= limit or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur, limit = w, rest_w
    if cur:
        lines.append(cur)
    return lines


class ResumeRenderer:
    def __init__(self, data, order, config=None):
        self.d = data
        self.order = order
        self.cfg = deepcopy(CONFIG)
        if config:
            self.cfg.update(config)
        self.warnings = []   # (where, message)

    # -- low-level drawing ---------------------------------------------------
    def _y(self, top, size):
        return PAGE_H - top - size * ASCENT

    def _text(self, c, x, top, txt, font, size, align="left",
              underline=False):
        y = self._y(top, size)
        w = stringWidth(txt, font, size)
        if align == "right":
            x -= w
        elif align == "center":
            x -= w / 2
        c.setFont(font, size)
        c.drawString(x, y, txt)
        if underline:
            c.setLineWidth(0.4)
            c.line(x, y - 1.3, x + w, y - 1.3)
        return x, w

    def _rule(self, c, top):
        cfg = self.cfg
        c.setLineWidth(cfg["rule_width"])
        c.line(cfg["rule_x0"], PAGE_H - top, cfg["rule_x1"], PAGE_H - top)

    def _check_fit(self, where, text, font, size, avail):
        w = stringWidth(text, font, size)
        if w > avail:
            over_mm = (w - avail) * 0.3528
            self.warnings.append(
                (where, f"wraps to 2 lines - {over_mm:.1f} mm too long: "
                        f"\u201c{text[:60]}\u2026\u201d"))
            return False
        return True

    # -- header ---------------------------------------------------------------
    def _header(self, c):
        cfg, h = self.cfg, self.d["header"]
        cx = PAGE_W / 2
        self._text(c, cx, cfg["name_top"], h["name"].upper(),
                   F_BOLD, cfg["name_size"], align="center")
        # contact line: phone . email(underlined) . linkedin(underlined)
        size = cfg["contact_size"]
        sep = "  \u2022  "
        parts = [(h["phone"], False), (sep, False), (h["email"], True),
                 (sep, False), (h["linkedin"], True)]
        total = sum(stringWidth(t, F_REG, size) for t, _ in parts)
        x = cx - total / 2
        for txt, ul in parts:
            _, w = self._text(c, x, cfg["contact_top"], txt, F_REG, size,
                              underline=ul)
            x += w
        self._text(c, cx, cfg["city_top"], h["city"], F_REG, size,
                   align="center")
        return cfg["city_top"] + cfg["header_to_first_rule"]

    # -- section bodies ---------------------------------------------------------
    def _experience(self, c, sec, top):
        cfg = self.cfg
        first = True
        for e in sec["entries"]:
            if not e.get("include", True):
                continue
            if not first:
                top += cfg["exp_entry_gap"] - cfg["exp_wrap_step"]
            first = False
            # header line: dates | COMPANY | location
            self._text(c, cfg["date_x"], top, e["dates"], F_REG, 10)
            self._text(c, cfg["col2_x"], top, e["company"], F_BOLD, 10)
            self._text(c, cfg["right_x"], top, e["location"], F_REG, 10,
                       align="right")
            # role line: (duration) | Role
            top += cfg["exp_header_to_role"]
            self._text(c, cfg["date_x"], top, e["duration"], F_ITAL, 10)
            self._text(c, cfg["col2_x"], top, e["role"], F_BI, 10)
            # bullets
            top += cfg["exp_role_to_bullet"]
            avail = cfg["right_x"] - cfg["bullet_text_x"]
            first = True
            for b in e["bullets"]:
                if not first:
                    top += cfg["exp_bullet_step"]
                first = False
                self._check_fit(f"{e['company']}", b, F_REG, 10, avail)
                lines = _wrap(b, F_REG, 10, avail, avail)
                y = self._y(top, 10)
                c.circle(cfg["bullet_dot_x"], y + 2.55,
                         cfg["bullet_radius"], stroke=0, fill=1)
                self._text(c, cfg["bullet_text_x"], top, lines[0], F_REG, 10)
                for extra in lines[1:]:
                    top += cfg["exp_wrap_step"]
                    self._text(c, cfg["bullet_text_x"], top, extra,
                               F_REG, 10)
            top += cfg["exp_wrap_step"]  # advance past last line
        return top - cfg["exp_wrap_step"]

    def _projects(self, c, sec, top):
        cfg = self.cfg
        first = True
        for e in sec["entries"]:
            if not e.get("include", True):
                continue
            if not first:
                top += cfg["proj_entry_gap"] - cfg["proj_wrap_step"]
            first = False
            # header line: date (left column, continues Experience/Education) | name
            self._text(c, cfg["date_x"], top, e["date"], F_ITAL, 10)
            self._text(c, cfg["col2_x"], top, e["name"], F_BOLD, 10)
            # bullets
            top += cfg["proj_header_to_bullet"]
            avail = cfg["right_x"] - cfg["bullet_text_x"]
            first = True
            for b in e["bullets"]:
                if not first:
                    top += cfg["proj_bullet_step"]
                first = False
                self._check_fit(f"{e['name']}", b, F_REG, 10, avail)
                lines = _wrap(b, F_REG, 10, avail, avail)
                y = self._y(top, 10)
                c.circle(cfg["bullet_dot_x"], y + 2.55,
                         cfg["bullet_radius"], stroke=0, fill=1)
                self._text(c, cfg["bullet_text_x"], top, lines[0], F_REG, 10)
                for extra in lines[1:]:
                    top += cfg["proj_wrap_step"]
                    self._text(c, cfg["bullet_text_x"], top, extra,
                               F_REG, 10)
            top += cfg["proj_wrap_step"]  # advance past last line
        return top - cfg["proj_wrap_step"]

    def _education(self, c, sec, top):
        cfg = self.cfg
        avail = cfg["right_x"] - cfg["col2_x"]
        first = True
        for e in sec["entries"]:
            if not e.get("include", True):
                continue
            if not first:
                top += cfg["edu_entry_gap"]
            first = False
            self._text(c, cfg["date_x"], top, e["dates"], F_REG, 10)
            self._text(c, cfg["col2_x"], top, e["school"], F_BOLD, 10)
            self._text(c, cfg["right_x"], top, e["location"], F_REG, 10,
                       align="right")
            lines = list(e["lines"])
            for j, ln in enumerate(lines):
                top += cfg["edu_line_step"]
                font = F_ITAL if j == 0 else F_REG   # degree line in italic
                if j == 0 and e.get("note") and e.get("note_include", True):
                    self._text(c, cfg["date_x"], top - 0.5, e["note"],
                               F_REG, cfg["edu_note_size"])
                self._check_fit(e["school"], ln, font, 10, avail)
                for k, seg in enumerate(_wrap(ln, font, 10, avail, avail)):
                    if k > 0:
                        top += cfg["edu_line_step"]
                    self._text(c, cfg["col2_x"], top, seg, font, 10)
        return top

    def _kv(self, c, sec, top):
        cfg = self.cfg
        avail = cfg["right_x"] - cfg["kv_content_x"]
        first = True
        for row in sec["rows"]:
            if not row.get("include", True):
                continue
            if not first:
                top += cfg["kv_row_step"]
            first = False
            self._text(c, cfg["kv_label_x"], top, row["label"], F_BOLD, 10)
            content = row["content"]
            self._check_fit(row["label"], content, F_REG, 10, avail)
            for k, seg in enumerate(_wrap(content, F_REG, 10, avail, avail)):
                if k > 0:
                    top += cfg["kv_row_step"]
                self._text(c, cfg["kv_content_x"], top, seg, F_REG, 10)
        return top

    def _bullets(self, c, sec, top):
        cfg = self.cfg
        avail = cfg["right_x"] - cfg["act_text_x"]
        first = True
        for item in sec["items"]:
            if not item.get("include", True):
                continue
            if not first:
                top += cfg["act_step"]
            first = False
            text = item["text"]
            self._check_fit(text, text, F_BOLD, 10, avail)
            y = self._y(top, 10)
            c.circle(cfg["act_dot_x"], y + 2.55, cfg["bullet_radius"],
                     stroke=0, fill=1)
            headline_lines = _wrap(text, F_BOLD, 10, avail, avail)
            self._text(c, cfg["act_text_x"], top, headline_lines[0],
                       F_BOLD, 10)
            for extra in headline_lines[1:]:
                top += cfg["act_step"]
                self._text(c, cfg["act_text_x"], top, extra, F_BOLD, 10)
            detail = item.get("detail", "")
            if detail:
                self._check_fit(text, detail, F_REG, 10, avail)
                for seg in _wrap(detail, F_REG, 10, avail, avail):
                    top += cfg["act_step"]
                    self._text(c, cfg["act_text_x"], top, seg, F_REG, 10)
        return top

    def _summary(self, c, sec, top):
        cfg = self.cfg
        avail = cfg["right_x"] - cfg["date_x"]
        text = sec.get("text", "")
        if not text:
            return top
        lines = _wrap(text, F_REG, 10, avail, avail)
        for i, ln in enumerate(lines):
            if i > 0:
                top += cfg["summary_line_step"]
            self._text(c, cfg["date_x"], top, ln, F_REG, 10)
        return top

    # -- main ------------------------------------------------------------------
    def render(self):
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.setTitle(self.d["header"]["name"])
        cfg = self.cfg

        rule_top = self._header(c)
        renderers = {"experience": self._experience,
                     "education": self._education,
                     "kv": self._kv,
                     "bullets": self._bullets,
                     "projects": self._projects,
                     "summary": self._summary}

        for key in self.order:
            sec = self.d["sections"].get(key)
            if not sec:
                continue
            self._rule(c, rule_top)
            title_top = rule_top + cfg["rule_to_title"]
            self._text(c, cfg["title_x"], title_top, sec["title"],
                       F_BOLD, cfg["title_size"])
            content_top = title_top + cfg["title_to_content"][sec["type"]]
            last_top = renderers[sec["type"]](c, sec, content_top)
            rule_top = last_top + cfg["section_gap"]

        if rule_top - cfg["section_gap"] > cfg["bottom_limit"]:
            over = (rule_top - cfg["section_gap"]
                    - cfg["bottom_limit"]) * 0.3528
            self.warnings.append(
                ("PAGE", f"content exceeds one page by ~{over:.1f} mm - "
                         f"remove a bullet or an entry"))
        c.showPage()
        c.save()
        return buf.getvalue()


def build_pdf(data, order, config=None):
    """Returns (pdf_bytes, warnings)."""
    r = ResumeRenderer(data, order, config)
    pdf = r.render()
    return pdf, r.warnings
