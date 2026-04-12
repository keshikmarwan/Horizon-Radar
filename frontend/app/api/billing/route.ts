import { NextResponse } from 'next/server';

export async function POST() {
  // Stripe integration stub for MVP.
  return NextResponse.json({
    status: 'stub',
    message: 'Stripe billing endpoint placeholder. Attach checkout session creation here.',
  });
}
