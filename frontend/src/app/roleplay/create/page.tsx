'use client';

import RouteProtection from '@/components/RouteProtection';
import RoleplayCreationWizard from '@/components/roleplay/RoleplayCreationWizard';

export default function CreateRoleplayPage() {
  return (
    <RouteProtection requireAuth={true} requireApproval={true}>
      <RoleplayCreationWizard />
    </RouteProtection>
  );
}
