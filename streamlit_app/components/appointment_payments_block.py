"""Bloque Abonos en la ficha de cita (layout tipo panel legacy)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Optional

import streamlit as st

from app.domain.appointment_money import appointment_financial_totals, format_cop
from streamlit_app import api_client


def _paid_on_display(pr: dict[str, Any]) -> str:
    pon = pr.get("paid_on")
    if isinstance(pon, date):
        return pon.strftime("%d/%m/%Y")
    if hasattr(pon, "strftime"):
        return pon.strftime("%d/%m/%Y")  # type: ignore[union-attr]
    if isinstance(pon, str) and len(pon) >= 10:
        try:
            return datetime.strptime(pon[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return pon[:10]
    ca = pr.get("created_at")
    if isinstance(ca, datetime):
        return ca.strftime("%d/%m/%Y")
    if isinstance(ca, str) and len(ca) >= 10:
        return ca[:10].replace("-", "/")
    return "—"


def _paid_on_iso(val: Any) -> Optional[str]:
    if hasattr(val, "isoformat"):
        return val.isoformat()[:10]  # type: ignore[union-attr]
    return None


def _map_payments_to_receipts(
    payments: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
) -> dict[int, int]:
    """Mapa abono (appointment_payments.id) → recibo PDF (vínculo BD o heurística)."""
    out: dict[int, int] = {}
    used_rids: set[int] = set()
    unlinked: list[dict[str, Any]] = []

    for rec in receipts:
        try:
            rid = int(rec.get("id") or 0)
            pid = int(rec.get("appointment_payment_id") or 0)
        except (TypeError, ValueError):
            continue
        if rid <= 0:
            continue
        if pid > 0:
            out[pid] = rid
            used_rids.add(rid)
        else:
            unlinked.append(rec)

    for pr in payments:
        try:
            pid = int(pr.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0 or pid in out:
            continue
        try:
            amt = float(pr.get("amount") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        note_l = str(pr.get("note") or "").strip().lower()

        for rec in unlinked:
            try:
                rid = int(rec.get("id") or 0)
            except (TypeError, ValueError):
                continue
            if rid in used_rids:
                continue
            try:
                rec_amt = float(rec.get("amount") or 0)
            except (TypeError, ValueError):
                continue
            if abs(rec_amt - amt) >= 0.01:
                continue
            kind = str(rec.get("kind") or "").strip().lower()
            if "inicial" in note_l and kind == "inicial":
                out[pid] = rid
                used_rids.add(rid)
                break
            if kind == "abono" and "inicial" not in note_l:
                out[pid] = rid
                used_rids.add(rid)
                break

        if pid not in out:
            for rec in unlinked:
                try:
                    rid = int(rec.get("id") or 0)
                except (TypeError, ValueError):
                    continue
                if rid not in used_rids:
                    out[pid] = rid
                    used_rids.add(rid)
                    break

    return out


def _load_receipts_for_appointment(
    aid: int,
    *,
    receipts_cache_prefix: str,
) -> tuple[bool, int, list[dict[str, Any]]]:
    list_key = f"{receipts_cache_prefix}{aid}"
    cached = st.session_state.get(list_key)
    if not isinstance(cached, tuple) or len(cached) != 3:
        cached = api_client.get_appointment_receipts(aid)
        st.session_state[list_key] = cached
    ok_r, code_r, raw = cached
    rows = [dict(x) for x in raw if isinstance(x, dict)] if ok_r and isinstance(raw, list) else []
    return bool(ok_r), int(code_r or 0), rows


def _fetch_receipt_pdf_cached(
    aid: int,
    receipt_id: int,
    *,
    receipt_pdf_cache_prefix: str,
) -> tuple[bool, bytes, str]:
    pdf_key = f"{receipt_pdf_cache_prefix}{aid}_{receipt_id}"
    hit = st.session_state.get(pdf_key)
    if isinstance(hit, tuple) and len(hit) == 2 and hit[0]:
        return True, hit[0], str(hit[1] or f"recibo_{aid}_{receipt_id}.pdf")
    ok_pdf, _pc, blob, fname = api_client.fetch_appointment_receipt_pdf(aid, receipt_id)
    if ok_pdf and blob:
        st.session_state[pdf_key] = (blob, fname)
        return True, blob, str(fname or f"recibo_{aid}_{receipt_id}.pdf")
    return False, b"", ""


def _resend_receipt_to_n8n(
    aid: int,
    receipt_id: int,
    *,
    queue_success: Callable[[str], None],
    api_error: Callable[[Any], str],
) -> None:
    with st.spinner("Reenviando recibo…"):
        ok, code, body = api_client.post_resend_appointment_receipt(aid, int(receipt_id))
    if ok:
        queue_success("**Recibo reenviado** (notificación enviada por n8n).")
        st.rerun()
    else:
        st.toast(f"No se pudo reenviar (HTTP {code}): {api_error(body)}", icon="❌")


def _pdf_first_page_png(blob: bytes, *, zoom: float = 1.35) -> bytes | None:
    """Primera página del PDF como PNG (PyMuPDF)."""
    try:
        import fitz  # pymupdf
    except ImportError:
        return None
    try:
        doc = fitz.open(stream=blob, filetype="pdf")
        if doc.page_count < 1:
            return None
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return pix.tobytes("png")
    except Exception:
        return None


def _render_inline_receipt_view(
    aid: int,
    receipt_id: int,
    *,
    receipt_pdf_cache_prefix: str,
    view_key: str,
    queue_success: Callable[[str], None],
    api_error: Callable[[Any], str],
) -> None:
    """Vista previa PDF dentro de la ficha (sin diálogo anidado)."""
    aid_s = str(aid)
    rid = int(receipt_id)
    if rid <= 0:
        st.session_state.pop(view_key, None)
        return

    st.markdown("---")
    st.markdown(f"**Recibo PDF** · #{rid}")

    with st.spinner("Cargando PDF…"):
        ok_pdf, blob, fname = _fetch_receipt_pdf_cached(
            aid, rid, receipt_pdf_cache_prefix=receipt_pdf_cache_prefix
        )

    if not ok_pdf or not blob:
        st.error("No se pudo cargar el recibo PDF.")
        if st.button("Cerrar", use_container_width=True, key=f"fcd_rec_view_close_err_{aid_s}_{rid}"):
            st.session_state.pop(view_key, None)
            st.rerun()
        return

    preview_png = _pdf_first_page_png(blob)
    if preview_png:
        st.image(preview_png, use_container_width=True)
    else:
        st.caption("No se pudo generar la vista previa. Descarga el PDF para abrirlo.")
    dl_col, res_col, close_col = st.columns([1.2, 1, 1])
    with dl_col:
        st.download_button(
            "Descargar PDF",
            data=blob,
            file_name=fname,
            mime="application/pdf",
            use_container_width=True,
            key=f"fcd_rec_dl_{aid_s}_{rid}",
            type="primary",
        )
    with res_col:
        if st.button(
            "Reenviar",
            use_container_width=True,
            key=f"fcd_rec_resend_{aid_s}_{rid}",
            help="Vuelve a enviar este PDF por n8n (WhatsApp / correo según flujo).",
        ):
            _resend_receipt_to_n8n(
                aid, rid, queue_success=queue_success, api_error=api_error
            )
    with close_col:
        if st.button("Cerrar vista", use_container_width=True, key=f"fcd_rec_view_close_{aid_s}_{rid}"):
            st.session_state.pop(view_key, None)
            st.rerun()


def render_appointment_abonos_section(
    *,
    aid: int,
    appointment_row: dict[str, Any],
    montos_locked: bool,
    today: date,
    get_payments_cached: Callable[[int], tuple[bool, int, Any]],
    purge_payment_caches: Callable[[], None],
    fin_payments_cache_prefix: str,
    receipts_cache_prefix: str,
    receipt_pdf_cache_prefix: str,
    queue_success: Callable[[str], None],
    api_error: Callable[[Any], str],
    seed_reload_key: str,
) -> None:
    """Abonos: alta en línea, tabla Fecha/Valor y edición por fila."""
    aid_s = str(aid)
    open_key = f"_fcd_abonos_open_{aid_s}"
    if open_key not in st.session_state:
        st.session_state[open_key] = True

    st.markdown('<div class="ap-pay-panel-root" aria-hidden="true"></div>', unsafe_allow_html=True)

    head_l, head_r = st.columns([5, 1], vertical_alignment="center")
    with head_l:
        st.markdown('<p class="ap-pay-panel-title">Abonos</p>', unsafe_allow_html=True)
    with head_r:
        collapsed = not bool(st.session_state.get(open_key, True))
        if st.button(
            "−" if not collapsed else "+",
            key=f"fcd_abonos_toggle_{aid_s}",
            help="Contraer o expandir abonos",
            use_container_width=True,
        ):
            st.session_state[open_key] = not st.session_state.get(open_key, True)
            st.rerun()

    if not st.session_state.get(open_key, True):
        return

    okp, pcode, pays_raw = get_payments_cached(aid)
    payments: list[dict[str, Any]] = (
        [dict(x) for x in pays_raw if isinstance(x, dict)] if okp and isinstance(pays_raw, list) else []
    )

    if not montos_locked:
        pay_row_live = appointment_row
        tot_for_pay = float(
            st.session_state.get(f"fcd_tot_{aid_s}") or pay_row_live.get("total_amount") or 0
        )
        _, dep_for_pay, pend_for_pay = appointment_financial_totals(
            {**pay_row_live, "total_amount": tot_for_pay}
        )
        can_add_pay = pend_for_pay > 0.009
        if not can_add_pay:
            st.info("Trabajo cubierto: no hay saldo pendiente; no se pueden agregar abonos adicionales.")

        dt_key = f"fcd_newpay_dt_{aid_s}"
        if dt_key not in st.session_state:
            st.session_state[dt_key] = today

        f_lbl, f_in, v_lbl, v_in, btn_add = st.columns([1.05, 1.15, 0.95, 1.15, 0.45], vertical_alignment="bottom")
        with f_lbl:
            st.markdown("**Fecha del abono:** *")
        with f_in:
            st.date_input(
                "Fecha del abono",
                min_value=today,
                format="DD/MM/YYYY",
                key=dt_key,
                label_visibility="collapsed",
                disabled=not can_add_pay,
            )
        with v_lbl:
            st.markdown("**Valor del abono** *")
        with v_in:
            st.number_input(
                "Valor del abono",
                min_value=0.0,
                max_value=float(pend_for_pay) if can_add_pay else 0.0,
                step=1000.0,
                key=f"fcd_newpay_am_{aid_s}",
                format="%.0f",
                label_visibility="collapsed",
                disabled=not can_add_pay,
            )
        with btn_add:
            if st.button(
                "",
                key=f"fcd_newpay_btn_{aid_s}",
                icon=":material/add:",
                type="primary",
                use_container_width=True,
                disabled=not can_add_pay,
            ):
                paid_date = st.session_state.get(dt_key)
                amt_add = float(int(st.session_state.get(f"fcd_newpay_am_{aid_s}") or 0))
                if amt_add <= 0:
                    st.toast("El abono debe ser mayor a cero.", icon="⚠️")
                elif amt_add > pend_for_pay + 0.01:
                    st.toast(
                        f"El abono no puede superar el saldo pendiente ({format_cop(pend_for_pay)}).",
                        icon="⚠️",
                    )
                else:
                    iso = _paid_on_iso(paid_date)
                    with st.spinner("Registrando abono…"):
                        ok_pay, cd_pay, body_pay = api_client.post_appointment_payment(
                            aid, amt_add, note=None, paid_on=iso
                        )
                    if ok_pay:
                        purge_payment_caches()
                        st.session_state.pop(f"{fin_payments_cache_prefix}{aid}", None)
                        st.session_state.pop(f"{receipts_cache_prefix}{aid}", None)
                        st.session_state.pop(seed_reload_key, None)
                        st.session_state["_ap_reload"] = True
                        queue_success(
                            "**Abono registrado.** Revisa PDF en **Recibos** cuando corresponda."
                        )
                        st.rerun()
                    else:
                        st.toast(f"Error HTTP {cd_pay}: {api_error(body_pay)}", icon="❌")

    if not okp:
        st.warning(f"No se cargaron abonos (HTTP {pcode}).")
        return

    ok_rec, code_rec, receipts = _load_receipts_for_appointment(
        aid, receipts_cache_prefix=receipts_cache_prefix
    )
    receipt_by_pay = _map_payments_to_receipts(payments, receipts) if ok_rec else {}
    view_key = f"_fcd_receipt_view_rid_{aid_s}"

    st.markdown('<p class="ap-ficha-section-band ap-pay-table-band">Abonos</p>', unsafe_allow_html=True)
    h1, h2, h3 = st.columns([1.15, 0.95, 1.05], vertical_alignment="center")
    h1.markdown('<span class="ap-ficha-col-head ap-pay-col-head">Fecha</span>', unsafe_allow_html=True)
    h2.markdown('<span class="ap-ficha-col-head ap-pay-col-head">Valor</span>', unsafe_allow_html=True)
    h3.markdown(
        '<span class="ap-ficha-col-head ap-pay-col-head ap-pay-col-head--actions">Acciones</span>',
        unsafe_allow_html=True,
    )

    if not payments:
        st.caption("Aún no hay abonos registrados.")
    else:
        if not ok_rec:
            st.caption(f"No se cargó el índice de recibos (HTTP {code_rec}).")
        edit_key = f"_fcd_pay_edit_{aid_s}"
        for idx, pr in enumerate(payments):
            pid = int(pr.get("id") or 0)
            if pid <= 0:
                continue
            amt = float(pr.get("amount") or 0)
            rid = receipt_by_pay.get(pid)
            c1, c2, c3 = st.columns([1.15, 0.95, 1.05], vertical_alignment="center")
            with c1:
                st.write(_paid_on_display(pr))
            with c2:
                st.write(f"{int(round(amt)):,}".replace(",", "."))
            with c3:
                a_view, a_send, a_edit = st.columns(3, gap="small", vertical_alignment="center")
                with a_view:
                    if st.button(
                        "",
                        key=f"fcd_pay_view_{aid_s}_{pid}",
                        icon=":material/picture_as_pdf:",
                        use_container_width=True,
                        disabled=not rid,
                        help=(
                            "Ver recibo PDF"
                            if rid
                            else (
                                "No hay recibo para este abono (abono en 0 al agendar o fallo al generar)."
                                if not receipts
                                else "Sin recibo PDF vinculado a este abono"
                            )
                        ),
                    ):
                        st.session_state[view_key] = int(rid)
                        st.rerun()
                with a_send:
                    if st.button(
                        "",
                        key=f"fcd_pay_resend_{aid_s}_{pid}",
                        icon=":material/send:",
                        use_container_width=True,
                        disabled=not rid,
                        help="Reenviar recibo" if rid else "Sin recibo para reenviar",
                    ):
                        _resend_receipt_to_n8n(
                            aid, int(rid), queue_success=queue_success, api_error=api_error
                        )
                with a_edit:
                    if st.button(
                        "",
                        key=f"fcd_pay_edit_btn_{aid_s}_{pid}",
                        icon=":material/edit:",
                        use_container_width=True,
                        disabled=montos_locked,
                        help="Editar abono",
                    ):
                        st.session_state[edit_key] = pid
                        pon = pr.get("paid_on")
                        if isinstance(pon, date):
                            st.session_state[f"fcd_patched_dt_{aid_s}_{pid}"] = pon
                        elif isinstance(pon, str) and len(pon) >= 10:
                            try:
                                st.session_state[f"fcd_patched_dt_{aid_s}_{pid}"] = datetime.strptime(
                                    pon[:10], "%Y-%m-%d"
                                ).date()
                            except ValueError:
                                st.session_state[f"fcd_patched_dt_{aid_s}_{pid}"] = today
                        else:
                            st.session_state[f"fcd_patched_dt_{aid_s}_{pid}"] = today
                        st.session_state[f"fcd_patched_am_{aid_s}_{pid}"] = float(
                            int(round(amt))
                        )
                        st.rerun()

        pid_edit = int(st.session_state.get(edit_key) or 0)
        if pid_edit > 0 and not montos_locked:
            pr_hit = next(
                (z for z in payments if int(z.get("id") or 0) == pid_edit),
                None,
            )
            if isinstance(pr_hit, dict):
                st.markdown("---")
                st.caption(f"Editar abono #{pid_edit}")
                e1, e2, e3 = st.columns([1.2, 1.2, 1], vertical_alignment="bottom")
                with e1:
                    st.date_input(
                        "Fecha del abono",
                        min_value=today,
                        format="DD/MM/YYYY",
                        key=f"fcd_patched_dt_{aid_s}_{pid_edit}",
                    )
                with e2:
                    st.number_input(
                        "Valor del abono (COP)",
                        min_value=1.0,
                        step=1000.0,
                        key=f"fcd_patched_am_{aid_s}_{pid_edit}",
                        format="%.0f",
                    )
                with e3:
                    if st.button(
                        "Guardar",
                        type="primary",
                        use_container_width=True,
                        key=f"fcd_patched_sv_{aid_s}_{pid_edit}",
                    ):
                        n_am = float(
                            int(st.session_state.get(f"fcd_patched_am_{aid_s}_{pid_edit}") or 0)
                        )
                        nd_dt = st.session_state.get(f"fcd_patched_dt_{aid_s}_{pid_edit}")
                        nd_iso = _paid_on_iso(nd_dt)
                        ok_u, cu, bu = api_client.patch_appointment_payment(
                            aid,
                            pid_edit,
                            amount=n_am,
                            paid_on=nd_iso,
                        )
                        if ok_u:
                            purge_payment_caches()
                            st.session_state.pop(f"{fin_payments_cache_prefix}{aid}", None)
                            st.session_state.pop(seed_reload_key, None)
                            st.session_state.pop(edit_key, None)
                            st.session_state["_ap_reload"] = True
                            queue_success("**Abono actualizado.**")
                            st.rerun()
                        else:
                            st.toast(f"Error HTTP {cu}: {api_error(bu)}", icon="❌")
                    if st.button(
                        "Cancelar",
                        use_container_width=True,
                        key=f"fcd_pay_edit_cancel_{aid_s}_{pid_edit}",
                    ):
                        st.session_state.pop(edit_key, None)
                        st.rerun()

    view_rid = int(st.session_state.get(view_key) or 0)
    if view_rid > 0:
        _render_inline_receipt_view(
            aid,
            view_rid,
            receipt_pdf_cache_prefix=receipt_pdf_cache_prefix,
            view_key=view_key,
            queue_success=queue_success,
            api_error=api_error,
        )


__all__ = ["render_appointment_abonos_section"]
