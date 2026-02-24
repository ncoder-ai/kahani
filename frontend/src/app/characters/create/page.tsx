import CharacterForm from '@/components/CharacterForm';
import RouteProtection from '@/components/RouteProtection';

export default function CreateCharacterPage() {
  return (
    <RouteProtection requireAuth={true} requireApproval={true}>
      <CharacterForm mode="create" />
    </RouteProtection>
  );
}
