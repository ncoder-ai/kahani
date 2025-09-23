from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db
from ..models import Character, StoryCharacter, User
from ..dependencies import get_current_user

router = APIRouter()

class CharacterCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    personality_traits: Optional[List[str]] = []
    background: Optional[str] = ""
    goals: Optional[str] = ""
    fears: Optional[str] = ""
    appearance: Optional[str] = ""
    is_template: Optional[bool] = True
    is_public: Optional[bool] = False

class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    personality_traits: Optional[List[str]] = None
    background: Optional[str] = None
    goals: Optional[str] = None
    fears: Optional[str] = None
    appearance: Optional[str] = None
    is_template: Optional[bool] = None
    is_public: Optional[bool] = None

class CharacterResponse(BaseModel):
    id: int
    name: str
    description: str
    personality_traits: List[str]
    background: str
    goals: str
    fears: str
    appearance: str
    is_template: bool
    is_public: bool
    creator_id: int
    created_at: str
    updated_at: Optional[str]

    class Config:
        from_attributes = True

@router.get("/", response_model=List[CharacterResponse])
async def get_characters(
    skip: int = 0,
    limit: int = 50,
    include_public: bool = True,
    templates_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's characters and optionally public characters"""
    
    query = db.query(Character)
    
    if include_public:
        # Get user's characters + public characters from others
        query = query.filter(
            (Character.creator_id == current_user.id) | 
            (Character.is_public == True)
        )
    else:
        # Only user's characters
        query = query.filter(Character.creator_id == current_user.id)
    
    if templates_only:
        query = query.filter(Character.is_template == True)
    
    characters = query.offset(skip).limit(limit).all()
    
    return [
        CharacterResponse(
            id=char.id,
            name=char.name,
            description=char.description or "",
            personality_traits=char.personality_traits or [],
            background=char.background or "",
            goals=char.goals or "",
            fears=char.fears or "",
            appearance=char.appearance or "",
            is_template=char.is_template,
            is_public=char.is_public,
            creator_id=char.creator_id,
            created_at=char.created_at.isoformat(),
            updated_at=char.updated_at.isoformat() if char.updated_at else None
        )
        for char in characters
    ]

@router.post("/", response_model=CharacterResponse)
async def create_character(
    character_data: CharacterCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new character"""
    
    character = Character(
        name=character_data.name,
        description=character_data.description,
        personality_traits=character_data.personality_traits,
        background=character_data.background,
        goals=character_data.goals,
        fears=character_data.fears,
        appearance=character_data.appearance,
        creator_id=current_user.id,
        is_template=character_data.is_template,
        is_public=character_data.is_public
    )
    
    db.add(character)
    db.commit()
    db.refresh(character)
    
    return CharacterResponse(
        id=character.id,
        name=character.name,
        description=character.description or "",
        personality_traits=character.personality_traits or [],
        background=character.background or "",
        goals=character.goals or "",
        fears=character.fears or "",
        appearance=character.appearance or "",
        is_template=character.is_template,
        is_public=character.is_public,
        creator_id=character.creator_id,
        created_at=character.created_at.isoformat(),
        updated_at=character.updated_at.isoformat() if character.updated_at else None
    )

@router.get("/{character_id}", response_model=CharacterResponse)
async def get_character(
    character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific character"""
    
    character = db.query(Character).filter(
        Character.id == character_id,
        (Character.creator_id == current_user.id) | (Character.is_public == True)
    ).first()
    
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found"
        )
    
    return CharacterResponse(
        id=character.id,
        name=character.name,
        description=character.description or "",
        personality_traits=character.personality_traits or [],
        background=character.background or "",
        goals=character.goals or "",
        fears=character.fears or "",
        appearance=character.appearance or "",
        is_template=character.is_template,
        is_public=character.is_public,
        creator_id=character.creator_id,
        created_at=character.created_at.isoformat(),
        updated_at=character.updated_at.isoformat() if character.updated_at else None
    )

@router.put("/{character_id}", response_model=CharacterResponse)
async def update_character(
    character_id: int,
    character_data: CharacterUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a character (only the creator can update)"""
    
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.creator_id == current_user.id
    ).first()
    
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found or you don't have permission to edit it"
        )
    
    # Update fields that were provided
    update_data = character_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(character, field, value)
    
    db.commit()
    db.refresh(character)
    
    return CharacterResponse(
        id=character.id,
        name=character.name,
        description=character.description or "",
        personality_traits=character.personality_traits or [],
        background=character.background or "",
        goals=character.goals or "",
        fears=character.fears or "",
        appearance=character.appearance or "",
        is_template=character.is_template,
        is_public=character.is_public,
        creator_id=character.creator_id,
        created_at=character.created_at.isoformat(),
        updated_at=character.updated_at.isoformat() if character.updated_at else None
    )

@router.delete("/{character_id}")
async def delete_character(
    character_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a character (only the creator can delete)"""
    
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.creator_id == current_user.id
    ).first()
    
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found or you don't have permission to delete it"
        )
    
    db.delete(character)
    db.commit()
    
    return {"message": "Character deleted successfully"}