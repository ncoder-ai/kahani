import { NextRequest, NextResponse } from 'next/server';

// Get BACKEND_URL lazily (only when route is called, not at build time)
function getBackendUrl(): string {
  const BACKEND_URL = process.env.BACKEND_URL;
  if (!BACKEND_URL) {
    throw new Error('BACKEND_URL environment variable must be set. Check your configuration.');
  }
  return BACKEND_URL;
}

export async function GET(request: NextRequest) {
  try {
    const BACKEND_URL = getBackendUrl();
    const authHeader = request.headers.get('authorization');
    
    const response = await fetch(`${BACKEND_URL}/api/settings/`, {
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
    console.error('Settings API error:', error);
    return NextResponse.json(
      { detail: 'Failed to fetch settings' },
      { status: 500 }
    );
  }
}

export async function PUT(request: NextRequest) {
  try {
    const BACKEND_URL = getBackendUrl();
    const authHeader = request.headers.get('authorization');
    const body = await request.json();

    const response = await fetch(`${BACKEND_URL}/api/settings/`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': authHeader || '',
      },
      body: JSON.stringify(body),
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error('Settings update API error:', error);
    return NextResponse.json(
      { detail: 'Failed to update settings' },
      { status: 500 }
    );
  }
}