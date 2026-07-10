"""Shared advanced-search filter builder for recipients, used by the search,
export, and distinct-values endpoints so their result sets always match.

Multi-select fields (industry, designation, skills, seniority level, country,
state, city, lead status, recipient groups, tags) combine multiple chosen
values with OR within that field, and every field combines with every other
field via AND — e.g. industry IN (IT, Healthcare) AND designation IN (VP,
Director) AND recipient_group IN (Jira Team) AND tag IN (Decision Maker).
"""

from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Query, Session

from app.models import CampaignRecipient, Recipient, RecipientGroupMember, RecipientTag

SORTABLE_FIELDS = {
    "name": Recipient.name,
    "email": Recipient.email,
    "company": Recipient.company,
    "designation": Recipient.designation,
    "industry": Recipient.industry,
    "department": Recipient.department,
    "created_at": Recipient.created_at,
}

# Fields exposed for the distinct-values endpoint (multi-select dropdown options).
DISTINCT_VALUE_FIELDS = {
    "industry": Recipient.industry,
    "designation": Recipient.designation,
    "designation_level": Recipient.designation_level,
    "skills": Recipient.skills,
    "country": Recipient.country,
    "state": Recipient.state,
    "city": Recipient.city,
    "department": Recipient.department,
    "company_size": Recipient.company_size,
    "lead_status": Recipient.status,
    "source": Recipient.source,
}


@dataclass
class RecipientSearchFilters:
    search: str = ""
    name: str = ""
    email: str = ""
    company: str = ""
    department: str = ""
    company_size: str = ""
    years_of_experience: str = ""
    email_domain: str = ""
    source: str = ""

    # Multi-select (OR within field)
    designation: list[str] = field(default_factory=list)
    industry: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    seniority_level: list[str] = field(default_factory=list)
    country: list[str] = field(default_factory=list)
    state: list[str] = field(default_factory=list)
    city: list[str] = field(default_factory=list)
    lead_status: list[str] = field(default_factory=list)
    group_ids: list[int] = field(default_factory=list)
    tag_ids: list[int] = field(default_factory=list)

    campaign_id: int | None = None
    campaign_status: str = ""
    sort_by: str = "name"
    sort_order: str = "asc"


def _multi_ilike(query: Query, column, values: list[str]) -> Query:
    values = [v for v in values if v]
    if not values:
        return query
    return query.filter(or_(*[column.ilike(f"%{v}%") for v in values]))


def build_query(db: Session, filters: RecipientSearchFilters) -> Query:
    query = db.query(Recipient)

    if filters.search:
        term = f"%{filters.search}%"
        query = query.filter(
            (Recipient.name.ilike(term))
            | (Recipient.email.ilike(term))
            | (Recipient.company.ilike(term))
        )

    query = _multi_ilike(query, Recipient.industry, filters.industry)
    query = _multi_ilike(query, Recipient.designation, filters.designation)
    query = _multi_ilike(query, Recipient.skills, filters.skills)
    query = _multi_ilike(query, Recipient.designation_level, filters.seniority_level)
    query = _multi_ilike(query, Recipient.country, filters.country)
    query = _multi_ilike(query, Recipient.state, filters.state)
    query = _multi_ilike(query, Recipient.city, filters.city)
    query = _multi_ilike(query, Recipient.status, filters.lead_status)

    single_ilike_fields = {
        "name": filters.name,
        "email": filters.email,
        "company": filters.company,
        "department": filters.department,
        "company_size": filters.company_size,
        "years_of_experience": filters.years_of_experience,
        "source": filters.source,
    }
    for field_name, value in single_ilike_fields.items():
        if value:
            query = query.filter(getattr(Recipient, field_name).ilike(f"%{value}%"))

    if filters.email_domain:
        query = query.filter(Recipient.email.ilike(f"%@{filters.email_domain}"))

    # Groups/tags use an IN-subquery (not a join) so a recipient belonging to
    # multiple selected groups/tags still appears exactly once in the results.
    if filters.group_ids:
        query = query.filter(
            Recipient.id.in_(
                select(RecipientGroupMember.recipient_id).where(
                    RecipientGroupMember.group_id.in_(filters.group_ids)
                )
            )
        )

    if filters.tag_ids:
        query = query.filter(
            Recipient.id.in_(
                select(RecipientTag.recipient_id).where(RecipientTag.tag_id.in_(filters.tag_ids))
            )
        )

    if filters.campaign_id is not None:
        cr_subquery = select(CampaignRecipient.recipient_id).where(
            CampaignRecipient.campaign_id == filters.campaign_id
        )
        if filters.campaign_status:
            cr_subquery = cr_subquery.where(CampaignRecipient.status == filters.campaign_status)
        query = query.filter(Recipient.id.in_(cr_subquery))

    sort_column = SORTABLE_FIELDS.get(filters.sort_by, Recipient.name)
    query = query.order_by(sort_column.desc() if filters.sort_order == "desc" else sort_column.asc())

    return query


def get_distinct_values(db: Session, field_name: str, limit: int = 200) -> list[str]:
    column = DISTINCT_VALUE_FIELDS.get(field_name)
    if column is None:
        return []
    rows = (
        db.query(column)
        .filter(column.isnot(None), column != "")
        .distinct()
        .order_by(column)
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows]
