"""
src/core/document_pipeline.py
Status of one day's paperwork — contact sheet, absence sheet, daily
report, order letter — for a single date. Used by ui/work_pipeline_screen.py
so the مسير sees at a glance what's done and what still needs attention,
instead of opening all daily screens to check by hand.
"""
from dataclasses import dataclass
from typing import List

from data.database import (
    get_all_order_letters, get_day_absences, get_day_contacts,
    get_daily_reception_record, get_daily_report,
)

DOC_CONTACT = "contact"
DOC_ABSENCE = "absence"
DOC_REPORT = "report"
DOC_ORDER_LETTER = "order_letter"
DOC_RECEPTION = "reception"


@dataclass
class PipelineItem:
    """One daily document's status for a given date."""
    key: str      # DOC_CONTACT / DOC_ABSENCE / DOC_REPORT
    label: str     # Arabic document name
    ready: bool
    detail: str    # Arabic status sentence shown under the label


def get_daily_pipeline_status(date_str: str) -> List[PipelineItem]:
    """Status of the 5 daily documents for date_str (YYYY-MM-DD)."""
    has_contact = bool(get_day_contacts(date_str))
    has_absence = bool(get_day_absences(date_str))
    report = get_daily_report(date_str)
    report_saved = report is not None and report.id is not None
    has_order_letter = any(
        letter.period_start <= date_str <= letter.period_end
        for letter in get_all_order_letters()
    )
    has_reception = get_daily_reception_record(date_str) is not None

    if report_saved:
        report_detail = "تم حفظ التقرير"
    elif has_contact or has_absence:
        report_detail = "الأرقام جاهزة — يبقى ملء لائحة المعاينة وحفظ التقرير"
    else:
        report_detail = "بانتظار ورقتي الاتصال والغياب أولاً"

    return [
        PipelineItem(
            key=DOC_CONTACT,
            label="ورقة الاتصال اليومية",
            ready=has_contact,
            detail="تم إدخال بيانات الحضور" if has_contact else "لم يتم إدخال بيانات الحضور بعد",
        ),
        PipelineItem(
            key=DOC_ABSENCE,
            label="ورقة الغياب اليومي",
            ready=has_absence,
            detail="تم إدخال بيانات الغياب" if has_absence else "لم يتم إدخال بيانات الغياب بعد",
        ),
        PipelineItem(
            key=DOC_REPORT,
            label="التقرير اليومي",
            ready=report_saved,
            detail=report_detail,
        ),
        PipelineItem(
            key=DOC_ORDER_LETTER,
            label="رسالة الطلبية",
            ready=has_order_letter,
            detail="هذا اليوم مشمول برسالة طلبية محفوظة" if has_order_letter
                   else "لا توجد رسالة طلبية تغطي هذا اليوم بعد",
        ),
        PipelineItem(
            key=DOC_RECEPTION,
            label="محضر التسلم اليومي",
            ready=has_reception,
            detail="تم حفظ محضر التسليم" if has_reception
                   else "لم يتم إنشاء محضر التسليم بعد",
        ),
    ]
