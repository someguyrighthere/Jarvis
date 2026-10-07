import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dampMotion, ease, gestureMotion, speakingSway, stanceMotion, speechPaths } from './speech_motion.mjs';

const event = { start: 1, duration: 1.82, prepare: 0.48, stroke: 0.46, hold: 0.16, recover: 0.72 };

test('stance shifts stay small and vanish when inactive', () => {
  for (let t = 0; t < 60; t += 0.05) {
    const pose = stanceMotion(t, 1);
    assert.ok(Math.abs(pose.hipX) <= 0.022);
    assert.ok(pose.hipY >= -0.005 && pose.hipY <= -0.004);
    assert.ok(stanceMotion(t, 0).hipX === 0);
    assert.equal(pose.footLift, 0);
  }
});

test('a foot adjustment lifts, plants, then lifts back without sliding during its hold', () => {
  const start = stanceMotion(12, 1, 0, 1);
  const swing = stanceMotion(12.6, 1, 0.6, 1);
  const plant = stanceMotion(14, 1, 2, 1);
  const hold = stanceMotion(18, 1, 6, 1);
  const back = stanceMotion(19.4, 1, 7.4, 1);
  const end = stanceMotion(20, 1, 8, 1);
  assert.equal(start.footX, 0);
  assert.ok(swing.footLift > 0.024 && back.footLift > 0.024);
  assert.equal(plant.footLift, 0);
  assert.equal(plant.footX, hold.footX);
  assert.equal(plant.footZ, hold.footZ);
  assert.equal(end.footLift, 0);
  assert.equal(end.footX, 0);
  assert.ok(plant.hipX < 0);
  assert.ok(stanceMotion(14, 1, 2, -1).hipX > 0);
});

test('speaking sway is subtle, slow, and scales smoothly out of speaking', () => {
  let minimum = Infinity;
  let maximum = -Infinity;
  for (let time = 0; time < 40; time += 0.05) {
    const full = speakingSway(time, 1);
    const half = speakingSway(time, 0.5);
    const next = speakingSway(time + 0.05, 1);
    assert.ok(Math.abs(full.lateral) <= 0.031);
    assert.ok(Math.abs(full.forward) <= 0.008);
    assert.ok(Math.abs(next.lateral - full.lateral) < 0.001);
    assert.equal(half.lateral, full.lateral * 0.5);
    assert.ok(speakingSway(time, 0).lateral === 0);
    minimum = Math.min(minimum, full.lateral);
    maximum = Math.max(maximum, full.lateral);
  }
  assert.ok(minimum < -0.02 && maximum > 0.02);
});

test('separate preparation, expressive stroke, hold and slower recovery', () => {
  assert.equal(gestureMotion(event, 0).lift, 0);
  assert.equal(gestureMotion(event, 1).lift, 0);
  assert.equal(gestureMotion(event, 1.24).travel, 0);
  assert.equal(gestureMotion(event, 1.48).lift, 1);
  const stroke = gestureMotion(event, 1.71);
  assert.ok(Math.abs(stroke.travel - 0.5) < 1e-10);
  assert.ok(stroke.accent > 0.99);
  assert.equal(gestureMotion(event, 2.05).travel, 1);
  assert.equal(gestureMotion(event, 3).lift, 0);
});

test('curves are bounded with near-zero endpoint velocity and acceleration', () => {
  for (let t = -1; t <= 4; t += 0.005) {
    for (const value of Object.values(gestureMotion(event, t))) {
      assert.ok(Number.isFinite(value) && value >= 0 && value <= 1);
    }
  }
  assert.ok(ease(0.001) < 1e-7);
  assert.ok(1 - ease(0.999) < 1e-7);
});

test('phrase-linked beats retain a low ready position instead of dropping both arms', () => {
  const linked = { ...event, link_next: 3.4 };
  assert.equal(gestureMotion(linked, 3).lift, 0.28);
  assert.equal(gestureMotion(linked, 3).travel, 0);
  assert.equal(gestureMotion(linked, 3.5).lift, 0);
  assert.equal(gestureMotion({ ...event, linked: true }, 1).lift, 0.28);
});

test('paths contain a real stroke and remain in a compact conversational space', () => {
  for (const path of Object.values(speechPaths)) {
    const excursion = Math.hypot(...path.end.map((value, i) => value - path.ready[i]));
    assert.ok(excursion > 0.035 && excursion < 0.15);
    for (const position of [path.ready, path.end]) {
      assert.ok(position[0] < 0.35 && position[1] < 0.5 && position[2] < 0.3);
    }
  }
});

test('interruption releases slowly rather than snapping to zero in a hidden-browser frame', () => {
  const current = { lift: 1, travel: 1, accent: 1, wrist: 1, fingers: 1 };
  const target = { lift: 0, travel: 0, accent: 0, wrist: 0, fingers: 0 };
  dampMotion(current, target, 0.05, false);
  assert.ok(current.lift > 0.8);
  for (let i = 0; i < 50; i++) dampMotion(current, target, 0.05, false);
  assert.ok(current.lift < 0.001);
});
