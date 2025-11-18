import { NextRequest, NextResponse } from 'next/server';

// Get BACKEND_URL lazily (only when route is called, not at build time)
function getBackendUrl(): string {
  const BACKEND_URL = process.env.BACKEND_URL;
  if (!BACKEND_URL) {
    throw new Error('BACKEND_URL environment variable must be set. Check your configuration.');
  }
  return BACKEND_URL;
}

export async function POST(request: NextRequest) {
  try {
    const BACKEND_URL = getBackendUrl();
    const authHeader = request.headers.get('authorization');

    const response = await fetch(`${BACKEND_URL}/api/settings/reset`, {
      method: 'POST',
      headers: {
        'Authorization': authHeader || '',
      },
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error('Settings reset API error:', error);
    return NextResponse.json(
      { detail: 'Failed to reset settings' },
      { status: 500 }
    );
  }
}