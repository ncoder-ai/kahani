'use client';

import { useParams } from 'next/navigation';
import CharacterForm from '@/components/CharacterForm';
import RouteProtection from '@/components/RouteProtection';

export default function EditCharacterPage() {
  const params = useParams();
  const characterId = parseInt(params.id as string);

  return (
    <RouteProtection requireAuth={true} requireApproval={true}>
      <CharacterForm key={characterId} characterId={characterId} mode="edit" />
    </RouteProtection>
  );
}