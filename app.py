"""
Resume Builder - Streamlit app
Run with:  streamlit run app.py
"""

import base64
import json
from copy import deepcopy
from pathlib import Path

import streamlit as st
from reportlab.pdfbase.pdfmetrics import stringWidth

from resume_engine import CONFIG, build_pdf, _wrap

DATA_FILE = Path(__file__).parent / "resume_data.json"

st.set_page_config(page_title="Resume Builder", layout="wide",
                   page_icon="\U0001F4C4")


# ---------------------------------------------------------------- state ----
def load_data():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


if "data" not in st.session_state:
    st.session_state.data = load_data()
data = st.session_state.data

SECTION_KEYS = list(data["sections"].keys())
SECTION_TITLES = {k: data["sections"][k]["title"] for k in SECTION_KEYS}

# ------------------------------------------------------------- sidebar ----
with st.sidebar:
    st.title("\U0001F4C4 Resume Builder")

    if "order" not in st.session_state:
        saved = data.get("order", SECTION_KEYS)
        st.session_state.order = [k for k in saved if k in SECTION_KEYS] \
            + [k for k in SECTION_KEYS if k not in saved]
    order = st.session_state.order

    if "include" not in st.session_state:
        st.session_state.include = {
            k: data["sections"][k].get("include", True) for k in SECTION_KEYS
        }
    include = st.session_state.include

    st.subheader("Section order")
    for i, key in enumerate(list(order)):
        c1, c2, c3, c4 = st.columns([0.5, 0.12, 0.12, 0.14])
        c1.write(f"**{i + 1}.** {SECTION_TITLES[key].title()}")
        if c2.button("▲", key=f"up{key}", disabled=i == 0):
            order[i - 1], order[i] = order[i], order[i - 1]
            st.rerun()
        if c3.button("▼", key=f"dn{key}",
                     disabled=i == len(order) - 1):
            order[i + 1], order[i] = order[i], order[i + 1]
            st.rerun()
        include[key] = c4.checkbox("on", value=include[key],
                                   key=f"in{key}",
                                   label_visibility="collapsed")

    with st.expander("⚙️ Fine-tune spacing (pt)"):
        cfg_over = {}
        cfg_over["section_gap"] = st.slider(
            "Gap before each section rule", 15.0, 40.0,
            CONFIG["section_gap"], 0.5)
        cfg_over["header_to_first_rule"] = st.slider(
            "Header → first section", 15.0, 40.0,
            CONFIG["header_to_first_rule"], 0.5)
        cfg_over["exp_entry_gap"] = st.slider(
            "Gap between experiences", 12.0, 30.0,
            CONFIG["exp_entry_gap"], 0.1)
        cfg_over["edu_entry_gap"] = st.slider(
            "Gap between schools", 12.0, 30.0,
            CONFIG["edu_entry_gap"], 0.1)
        cfg_over["exp_bullet_step"] = st.slider(
            "Bullet line height", 11.0, 18.0,
            CONFIG["exp_bullet_step"], 0.1)

    with st.expander("🔧 Details"):
        st.caption("Small extras that don't belong in a normal section.")

        edu_entries = data["sections"].get("education", {}).get("entries", [])
        noted = [e for e in edu_entries if e.get("note")]
        if noted:
            st.markdown("**Expected graduation note**")
            for ei, e in enumerate(noted):
                e["note_include"] = st.checkbox(
                    f"Show “{e['note']}” ({e['school'].title()})",
                    value=e.get("note_include", True),
                    key=f"noteinc{ei}")

        st.markdown("**Address**")
        data["header"]["city"] = st.text_input(
            "Header address line", data["header"]["city"], key="hdr_city")

    if st.button("\U0001F4BE Save content & order to JSON",
                 use_container_width=True):
        data["order"] = order
        for key in SECTION_KEYS:
            data["sections"][key]["include"] = include[key]
        DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        st.success("Saved to resume_data.json")


BODY = 10
MM = 0.3528


def fit_meter(text, font, avail, label=""):
    """Show a one-line-fit indicator for a given text."""
    w = stringWidth(text, font, BODY)
    pct = w / avail
    if pct <= 1:
        st.progress(min(pct, 1.0),
                    text=f"{label} fits – {pct * 100:.0f}% of the line "
                         f"({(avail - w) * MM:.1f} mm spare)")
    else:
        st.error(f"{label} is {(w - avail) * MM:.1f} mm too long "
                 f"→ will wrap to 2 lines")


# ------------------------------------------------------------ main area ----
left, right = st.columns([0.52, 0.48])

with left:
    st.header("Content")
    st.caption("Untick “Include” on an entry to leave it out of the "
               "exported resume.")

    for key in order:
        if not include[key]:
            continue
        sec = data["sections"][key]
        with st.expander(f"**{sec['title']}**", expanded=False):

            if sec["type"] == "summary":
                avail = CONFIG["right_x"] - CONFIG["date_x"]
                txt = st.text_area(
                    "Summary paragraph",
                    sec.get("text", ""), key=f"sumtxt{key}", height=100)
                sec["text"] = txt.strip()
                if sec["text"]:
                    n_lines = len(_wrap(sec["text"], "Times-Roman", BODY,
                                        avail, avail))
                    st.caption(f"Wraps to {n_lines} line(s) on the resume.")

            elif sec["type"] == "experience":
                for ei, e in enumerate(sec["entries"]):
                    hdr, chk = st.columns([0.75, 0.25])
                    hdr.markdown(f"**{e['company']}** – {e['dates']}")
                    e["include"] = chk.checkbox(
                        "Include", value=e.get("include", True),
                        key=f"einc{key}{ei}")
                    e["role"] = st.text_input(
                        "Title", e["role"], key=f"erole{key}{ei}")
                    fit_meter(e["role"], "Times-BoldItalic",
                              CONFIG["right_x"] - CONFIG["col2_x"], "Title")
                    txt = st.text_area(
                        "Bullets (one per line)",
                        "\n".join(e["bullets"]), key=f"b{key}{ei}",
                        height=110)
                    e["bullets"] = [l.strip() for l in txt.splitlines()
                                    if l.strip()]
                    avail = CONFIG["right_x"] - CONFIG["bullet_text_x"]
                    for bi, b in enumerate(e["bullets"]):
                        fit_meter(b, "Times-Roman", avail, f"Bullet {bi+1}")
                    st.divider()

            elif sec["type"] == "projects":
                for ei, e in enumerate(sec["entries"]):
                    hdr, chk = st.columns([0.75, 0.25])
                    hdr.markdown(f"**{e['name']}** – {e['date']}")
                    e["include"] = chk.checkbox(
                        "Include", value=e.get("include", True),
                        key=f"pinc{key}{ei}")
                    txt = st.text_area(
                        "Bullets (one per line)",
                        "\n".join(e["bullets"]), key=f"pb{key}{ei}",
                        height=110)
                    e["bullets"] = [l.strip() for l in txt.splitlines()
                                    if l.strip()]
                    avail = CONFIG["right_x"] - CONFIG["bullet_text_x"]
                    for bi, b in enumerate(e["bullets"]):
                        fit_meter(b, "Times-Roman", avail, f"Bullet {bi+1}")
                    st.divider()

            elif sec["type"] == "education":
                for ei, e in enumerate(sec["entries"]):
                    hdr, chk = st.columns([0.75, 0.25])
                    hdr.markdown(f"**{e['school']}** – {e['dates']}")
                    e["include"] = chk.checkbox(
                        "Include", value=e.get("include", True),
                        key=f"educinc{key}{ei}")
                    txt = st.text_area(
                        "Lines (first = degree, italic)",
                        "\n".join(e["lines"]), key=f"l{key}{ei}",
                        height=110)
                    e["lines"] = [l.strip() for l in txt.splitlines()
                                  if l.strip()]
                    avail = CONFIG["right_x"] - CONFIG["col2_x"]
                    for li, l in enumerate(e["lines"]):
                        f = "Times-Italic" if li == 0 else "Times-Roman"
                        fit_meter(l, f, avail, f"Line {li+1}")
                    st.divider()

            elif sec["type"] == "kv":
                avail = CONFIG["right_x"] - CONFIG["kv_content_x"]
                for ri, row in enumerate(sec["rows"]):
                    c1, c2 = st.columns([0.75, 0.25])
                    val = c1.text_input(row["label"], row["content"],
                                        key=f"kv{key}{ri}")
                    row["content"] = val
                    row["include"] = c2.checkbox(
                        "Include", value=row.get("include", True),
                        key=f"kvinc{key}{ri}")
                    fit_meter(val, "Times-Roman", avail, row["label"])

            elif sec["type"] == "bullets":
                avail = CONFIG["right_x"] - CONFIG["act_text_x"]
                for ii, item in enumerate(sec["items"]):
                    hdr, chk = st.columns([0.75, 0.25])
                    hdr.markdown(f"**Item {ii + 1}**")
                    item["include"] = chk.checkbox(
                        "Include", value=item.get("include", True),
                        key=f"acinc{key}{ii}")
                    val = st.text_input(
                        "Headline (bold)", item["text"], key=f"ac{key}{ii}")
                    item["text"] = val
                    fit_meter(val, "Times-Bold", avail, "Headline")
                    detail = st.text_input(
                        "Description (optional, regular weight)",
                        item.get("detail", ""), key=f"acd{key}{ii}")
                    item["detail"] = detail
                    if detail:
                        fit_meter(detail, "Times-Roman", avail,
                                  "Description")
                    st.divider()

with right:
    st.header("Preview & export")
    active_order = [k for k in order if include[k]]
    pdf_bytes, warnings = build_pdf(deepcopy(data), active_order, cfg_over)

    for where, msg in warnings:
        st.warning(f"**{where}**: {msg}")
    if not warnings:
        st.success("Every line fits on one line – single page ✓")

    st.download_button(
        "⬇️ Download CV.pdf",
        pdf_bytes,
        file_name=f"CV_{data['header']['name'].replace(' ', '_')}.pdf",
        mime="application/pdf", type="primary",
        use_container_width=True)

    b64 = base64.b64encode(pdf_bytes).decode()
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}#toolbar=0" '
        f'width="100%" height="820" style="border:1px solid #ddd;'
        f'border-radius:6px;"></iframe>',
        unsafe_allow_html=True)
