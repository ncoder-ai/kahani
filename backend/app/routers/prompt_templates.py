from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.prompt_template import PromptTemplate
from app.models.user import User
from app.dependencies import get_current_user
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

# Pydantic models for request/response
class PromptTemplateBase(BaseModel):
    template_key: str
    name: str
    description: Optional[str] = None
    category: str
    system_prompt: str
    user_prompt_template: Optional[str] = None
    is_active: bool = True
    max_tokens: int = 2048

class PromptTemplateCreate(PromptTemplateBase):
    pass

class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    is_active: Optional[bool] = None
    max_tokens: Optional[int] = None

class PromptTemplateResponse(PromptTemplateBase):
    id: int
    user_id: int
    is_default: bool
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

@router.get("/", response_model=List[PromptTemplateResponse])
def get_prompt_templates(
    category: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all prompt templates for the current user"""
    query = db.query(PromptTemplate).filter(
        (PromptTemplate.user_id == current_user.id) | 
        (PromptTemplate.is_default == True)
    )
    
    if category:
        query = query.filter(PromptTemplate.category == category)
    if active_only:
        query = query.filter(PromptTemplate.is_active == True)
    
    return query.all()

@router.get("/by-key/{template_key}", response_model=PromptTemplateResponse)
def get_prompt_template_by_key(
    template_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific prompt template by key"""
    template = db.query(PromptTemplate).filter(
        PromptTemplate.template_key == template_key,
        (PromptTemplate.user_id == current_user.id) | 
        (PromptTemplate.is_default == True),
        PromptTemplate.is_active == True
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    
    return template

@router.get("/{template_id}", response_model=PromptTemplateResponse)
def get_prompt_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific prompt template by ID"""
    template = db.query(PromptTemplate).filter(
        PromptTemplate.id == template_id,
        (PromptTemplate.user_id == current_user.id) | 
        (PromptTemplate.is_default == True)
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    
    return template

@router.post("/", response_model=PromptTemplateResponse)
def create_prompt_template(
    template: PromptTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new prompt template"""
    # Check if template_key already exists for this user
    existing = db.query(PromptTemplate).filter(
        PromptTemplate.template_key == template.template_key,
        PromptTemplate.user_id == current_user.id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Template with key '{template.template_key}' already exists"
        )
    
    db_template = PromptTemplate(
        user_id=current_user.id,
        template_key=template.template_key,
        name=template.name,
        description=template.description,
        category=template.category,
        system_prompt=template.system_prompt,
        user_prompt_template=template.user_prompt_template,
        is_default=False,
        is_active=template.is_active,
        max_tokens=template.max_tokens
    )
    
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    
    return db_template

@router.put("/{template_id}", response_model=PromptTemplateResponse)
def update_prompt_template(
    template_id: int,
    template_update: PromptTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing prompt template"""
    template = db.query(PromptTemplate).filter(
        PromptTemplate.id == template_id,
        PromptTemplate.user_id == current_user.id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    
    if template.is_default:
        raise HTTPException(status_code=403, detail="Cannot modify default templates")
    
    update_data = template_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)
    
    template.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(template)
    
    return template

@router.delete("/{template_id}")
def delete_prompt_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a prompt template"""
    template = db.query(PromptTemplate).filter(
        PromptTemplate.id == template_id,
        PromptTemplate.user_id == current_user.id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    
    if template.is_default:
        raise HTTPException(status_code=403, detail="Cannot delete default templates")
    
    db.delete(template)
    db.commit()
    
    return {"message": "Prompt template deleted successfully"}

@router.post("/{template_id}/clone", response_model=PromptTemplateResponse)
def clone_prompt_template(
    template_id: int,
    new_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Clone an existing prompt template"""
    original = db.query(PromptTemplate).filter(
        PromptTemplate.id == template_id,
        (PromptTemplate.user_id == current_user.id) | 
        (PromptTemplate.is_default == True)
    ).first()
    
    if not original:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    
    # Generate a unique template key
    base_key = original.template_key
    counter = 1
    new_key = f"{base_key}_copy"
    
    while db.query(PromptTemplate).filter(
        PromptTemplate.template_key == new_key,
        PromptTemplate.user_id == current_user.id
    ).first():
        counter += 1
        new_key = f"{base_key}_copy_{counter}"
    
    cloned = PromptTemplate(
        user_id=current_user.id,
        template_key=new_key,
        name=new_name or f"{original.name} (Copy)",
        description=original.description,
        category=original.category,
        system_prompt=original.system_prompt,
        user_prompt_template=original.user_prompt_template,
        is_default=False,
        is_active=True,
        max_tokens=original.max_tokens
    )
    
    db.add(cloned)
    db.commit()
    db.refresh(cloned)
    
    return cloned

@router.get("/categories/list")
def get_prompt_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of all prompt categories"""
    categories = db.query(PromptTemplate.category).filter(
        (PromptTemplate.user_id == current_user.id) | 
        (PromptTemplate.is_default == True),
        PromptTemplate.is_active == True
    ).distinct().all()
    
    return [cat[0] for cat in categories]