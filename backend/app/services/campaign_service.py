"""Campaign CRUD business logic."""

from sqlalchemy.orm import Session

from app.models import Campaign, CampaignSequenceStage, Template
from app.schemas.schemas import CampaignCreate, CampaignSequenceStageCreate, CampaignUpdate


class CampaignService:
    def create(self, db: Session, data: CampaignCreate, user_id: int | None = None) -> Campaign:
        existing = db.query(Campaign).filter(Campaign.campaign_id == data.campaign_id).first()
        if existing:
            raise ValueError(f"Campaign ID '{data.campaign_id}' already exists")

        campaign = Campaign(
            campaign_name=data.campaign_name,
            campaign_id=data.campaign_id,
            description=data.description,
            owner=data.owner,
            department=data.department,
            target_audience=data.target_audience,
            subject=data.subject,
            status=data.status,
            user_id=user_id,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return campaign

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> list[Campaign]:
        return (
            db.query(Campaign)
            .order_by(Campaign.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_id(self, db: Session, campaign_id: int) -> Campaign | None:
        return db.query(Campaign).filter(Campaign.id == campaign_id).first()

    def get_template(self, db: Session, campaign_id: int) -> Template | None:
        return (
            db.query(Template)
            .filter(Template.campaign_id == campaign_id)
            .order_by(Template.created_at.desc())
            .first()
        )

    def update(self, db: Session, campaign_id: int, data: CampaignUpdate) -> Campaign:
        campaign = self.get_by_id(db, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(campaign, field, value)

        db.commit()
        db.refresh(campaign)
        return campaign

    def delete(self, db: Session, campaign_id: int) -> None:
        campaign = self.get_by_id(db, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")
        db.delete(campaign)
        db.commit()

    def save_template(self, db: Session, campaign_id: int, template_data: dict) -> Template:
        campaign = self.get_by_id(db, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")

        # Replace existing template for this campaign
        db.query(Template).filter(Template.campaign_id == campaign_id).delete()

        template = Template(
            campaign_id=campaign_id,
            type=template_data["type"],
            subject=template_data["subject"],
            body=template_data["body"],
            closing=template_data.get("closing"),
            cta=template_data.get("cta"),
        )
        db.add(template)

        if template_data.get("subject"):
            campaign.subject = template_data["subject"]

        db.commit()
        db.refresh(template)
        return template

    def list_sequence_stages(self, db: Session, campaign_id: int) -> list[CampaignSequenceStage]:
        return (
            db.query(CampaignSequenceStage)
            .filter(CampaignSequenceStage.campaign_id == campaign_id)
            .order_by(CampaignSequenceStage.stage_order)
            .all()
        )

    def create_sequence_stage(
        self, db: Session, campaign_id: int, data: CampaignSequenceStageCreate
    ) -> CampaignSequenceStage:
        if not self.get_by_id(db, campaign_id):
            raise ValueError("Campaign not found")

        existing = (
            db.query(CampaignSequenceStage)
            .filter(
                CampaignSequenceStage.campaign_id == campaign_id,
                CampaignSequenceStage.stage_order == data.stage_order,
            )
            .first()
        )
        if existing:
            raise ValueError(f"Stage order {data.stage_order} already exists for this campaign")

        stage = CampaignSequenceStage(campaign_id=campaign_id, **data.model_dump())
        db.add(stage)
        db.commit()
        db.refresh(stage)
        return stage

    def update_sequence_stage(self, db: Session, stage_id: int, update_data: dict) -> CampaignSequenceStage:
        stage = db.query(CampaignSequenceStage).filter(CampaignSequenceStage.id == stage_id).first()
        if not stage:
            raise ValueError("Sequence stage not found")
        for field, value in update_data.items():
            setattr(stage, field, value)
        db.commit()
        db.refresh(stage)
        return stage

    def delete_sequence_stage(self, db: Session, stage_id: int) -> None:
        stage = db.query(CampaignSequenceStage).filter(CampaignSequenceStage.id == stage_id).first()
        if not stage:
            raise ValueError("Sequence stage not found")
        db.delete(stage)
        db.commit()
