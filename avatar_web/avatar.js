import * as THREE from 'three';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { TGALoader } from 'three/addons/loaders/TGALoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { dampMotion, gestureMotion, speakingSway, stanceMotion, speechPaths } from './speech_motion.mjs';

const status = document.querySelector('#status');
const error = document.querySelector('#error');
const stage = document.querySelector('#stage');
const text = (id, value) => { document.getElementById(id).textContent = value; };
const scene = new THREE.Scene();
const backdrop = document.createElement('canvas');
backdrop.width = 1100;
backdrop.height = 900;
const backdropContext = backdrop.getContext('2d');
const backgroundGradient = backdropContext.createRadialGradient(550, 400, 0, 550, 400, 720);
backgroundGradient.addColorStop(0, '#14283e');
backgroundGradient.addColorStop(0.35, '#0b1829');
backgroundGradient.addColorStop(0.7, '#040a13');
backgroundGradient.addColorStop(1, '#010306');
backdropContext.fillStyle = backgroundGradient;
backdropContext.fillRect(0, 0, backdrop.width, backdrop.height);
scene.background = new THREE.CanvasTexture(backdrop);
scene.background.colorSpace = THREE.SRGBColorSpace;
const camera = new THREE.PerspectiveCamera(35, stage.clientWidth / stage.clientHeight, 0.01, 100);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(stage.clientWidth, stage.clientHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
stage.append(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enablePan = false;
controls.minDistance = 1;
controls.maxDistance = 8;
scene.add(new THREE.HemisphereLight(0xe3f5ff, 0x29303e, 2.5));
const key = new THREE.DirectionalLight(0xffffff, 3);
key.position.set(2, 4, 3);
key.castShadow = true;
key.shadow.mapSize.set(1024, 1024);
key.shadow.camera.left = -2;
key.shadow.camera.right = 2;
key.shadow.camera.top = 2;
key.shadow.camera.bottom = -2;
key.shadow.camera.near = 0.1;
key.shadow.camera.far = 10;
key.shadow.normalBias = 0.015;
scene.add(key);
const rim = new THREE.DirectionalLight(0xb2edf4, 3);
rim.position.set(-2, 2, -2);
scene.add(rim);
const fill = new THREE.DirectionalLight(0xe5efff, 2);
fill.position.set(-3, 2, 3);
scene.add(fill);
const floor = new THREE.Mesh(new THREE.PlaneGeometry(20, 20),
  new THREE.ShadowMaterial({ opacity: 0.22, depthWrite: false }));
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

const base = '/assets/avatars/business-female-01/';
const manager = new THREE.LoadingManager();
manager.addHandler(/\.tga$/i, new TGALoader(manager));
manager.setURLModifier(url => {
  const normalized = url.replaceAll('\\', '/');
  if (/\.tga$/i.test(normalized)) return `${base}Textures/${normalized.split('/').pop()}`;
  return url;
});
manager.onError = url => { error.textContent = `Could not load avatar asset: ${url}`; };
let avatar;
const mouths = [];
const blinks = [];
const movingBones = [];
const gestureArms = [];
const stanceLegs = [];
let bodyRoot;
let rootRest;
let pelvisRest;
let stanceBlend = 0;
let stanceSeconds = 0;
let stepStarted = -100;
let nextStep = 12;
let stepSide = -1;
let listeningBlend = 0;
let speakingBlend = 0;
let idleSeconds = 0;
let wristBlend = 0;
let waitingBlend = 0;
let settlingSway = 0;
let glanceBlend = 0;
let stretchBlend = 0;
let postureBlend = 0;
let frontHandsBlend = 0;
let backHandsBlend = 0;
let snapshot = null;
let assistantRunning = null;
let receivedAt = 0;
let nextBlink = 2;
let blinkStarted = -100;
let elapsed = 0;
const clock = new THREE.Clock();
export { avatar, mouths, blinks, movingBones, gestureArms, stanceLegs };

const speechMotion = new Map();

export function gestureWeight(event, seconds) {
  return gestureMotion(event, seconds).lift;
}

function rotateWorld(bone, axis, angle) {
  const localAxis = axis.clone().applyQuaternion(bone.parent.getWorldQuaternion(new THREE.Quaternion()).invert());
  bone.quaternion.premultiply(new THREE.Quaternion().setFromAxisAngle(localAxis, angle));
  bone.updateWorldMatrix(false, true);
}

function aimBone(bone, child, target, weight) {
  if (weight <= 0) return;
  const inverseParent = bone.parent.getWorldQuaternion(new THREE.Quaternion()).invert();
  const current = child.getWorldPosition(new THREE.Vector3())
    .sub(bone.getWorldPosition(new THREE.Vector3())).normalize().applyQuaternion(inverseParent);
  const desired = target.clone().normalize().applyQuaternion(inverseParent);
  const rotation = new THREE.Quaternion().setFromUnitVectors(current, desired);
  bone.quaternion.premultiply(new THREE.Quaternion().slerp(rotation, weight));
  bone.updateWorldMatrix(false, true);
}

function idlePulse(start, duration, period = 72) {
  const phase = idleSeconds % period - start;
  return phase > 0 && phase < duration ? Math.sin(Math.PI * phase / duration) ** 2 : 0;
}

function idleHold(start, duration) {
  const phase = idleSeconds % 72 - start;
  if (phase <= 0 || phase >= duration) return 0;
  return THREE.MathUtils.smoothstep(phase, 0, 2)
    * (1 - THREE.MathUtils.smoothstep(phase, duration - 2, duration));
}

function orientHand(arm, forward, palm, weight) {
  if (weight < 0.0001) return;
  const x = forward.clone().normalize();
  const forearm = arm.hand.getWorldPosition(new THREE.Vector3())
    .sub(arm.lower.getWorldPosition(new THREE.Vector3())).normalize();
  const bend = forearm.angleTo(x);
  if (bend > 0.44) {
    const limited = new THREE.Quaternion().slerp(
      new THREE.Quaternion().setFromUnitVectors(forearm, x), 0.44 / bend);
    x.copy(forearm).applyQuaternion(limited);
  }
  const y = palm.clone().addScaledVector(x, -palm.dot(x)).normalize();
  const z = new THREE.Vector3().crossVectors(x, y).normalize();
  const world = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
  const local = arm.hand.parent.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(world);
  arm.hand.quaternion.slerp(local, weight);
  arm.hand.updateWorldMatrix(false, true);
}

function poseLimbAtTarget(arm, target, weight, pole, reachMargin = 0.001) {
  if (weight < 0.0001) return;
  const shoulder = arm.upper.getWorldPosition(new THREE.Vector3());
  const elbow = arm.lower.getWorldPosition(new THREE.Vector3());
  const wrist = arm.hand.getWorldPosition(new THREE.Vector3());
  const upperLength = shoulder.distanceTo(elbow);
  const lowerLength = elbow.distanceTo(wrist);
  const direction = target.clone().sub(shoulder);
  const distance = THREE.MathUtils.clamp(direction.length(),
    Math.abs(upperLength - lowerLength) + reachMargin, upperLength + lowerLength - reachMargin);
  direction.normalize();
  const along = (upperLength ** 2 - lowerLength ** 2 + distance ** 2) / (2 * distance);
  const outward = pole.clone();
  outward.addScaledVector(direction, -outward.dot(direction)).normalize();
  const elbowTarget = shoulder.clone().addScaledVector(direction, along)
    .addScaledVector(outward, Math.sqrt(Math.max(0, upperLength ** 2 - along ** 2)));
  aimBone(arm.upper, arm.lower, elbowTarget.sub(shoulder), weight);
  const reachable = shoulder.clone().addScaledVector(direction, distance);
  aimBone(arm.lower, arm.hand, reachable.sub(arm.lower.getWorldPosition(new THREE.Vector3())), weight);
}

function poseHandsTogether(arm, behind, weight) {
  if (weight < 0.0001) return;
  const pelvis = avatar.getObjectByName('Bip01_Pelvis').getWorldPosition(new THREE.Vector3());
  const target = pelvis.add(new THREE.Vector3(arm.side * 0.07,
    (behind ? 0.04 : 0.1) + arm.side * 0.015, (behind ? -0.2 : 0.23) + arm.side * 0.018));
  poseLimbAtTarget(arm, target, weight, new THREE.Vector3(arm.side, 0, 0));
  orientHand(arm, new THREE.Vector3(-arm.side, -0.25, 0),
    new THREE.Vector3(0, 0, behind ? 1 : -1), weight);
}

export function animateBody(delta, activity, time = elapsed, speech = snapshot?.speech,
  speechSeconds = snapshot ? snapshot.server_time + (performance.now() - receivedAt) / 1000 - (speech?.started_at || 0) : 0) {
  if (!avatar) return;
  speakingBlend = THREE.MathUtils.damp(speakingBlend, activity === 'SPEAKING' ? 1 : 0, 2, delta);
  listeningBlend = THREE.MathUtils.damp(listeningBlend, activity === 'LISTENING' ? 1 : 0, 2, delta);
  const waiting = ['IDLE', 'LISTENING', 'STANDBY'].includes(activity);
  const stanceActive = waiting || activity === 'SPEAKING';
  stanceSeconds += delta;
  if (stanceSeconds >= nextStep && stanceSeconds - stepStarted >= 8) {
    if (stanceActive) {
      stepStarted = stanceSeconds;
      stepSide *= -1;
    }
    nextStep = stanceSeconds + 32;
  }
  const stepping = stanceSeconds - stepStarted < 8;
  stanceBlend = THREE.MathUtils.damp(stanceBlend, stanceActive || stepping ? 1 : 0, 2, delta);
  waitingBlend = THREE.MathUtils.damp(waitingBlend, waiting ? 1 : 0, 2, delta);
  idleSeconds = waiting ? idleSeconds + delta : 0;
  const wristPhase = (idleSeconds - 12) % 36;
  const wristTarget = idleSeconds >= 12 && wristPhase < 4
    ? Math.sin(Math.PI * wristPhase / 4) ** 2 : 0;
  wristBlend = THREE.MathUtils.damp(wristBlend, wristTarget, 5, delta);
  const settlePhase = wristPhase - 4.5;
  const settleTarget = idleSeconds >= 12 && settlePhase > 0 && settlePhase < 6
    ? Math.sin(Math.PI * settlePhase / 6) ** 2 * Math.sin(settlePhase * Math.PI / 3) * 0.022 : 0;
  settlingSway = THREE.MathUtils.damp(settlingSway, settleTarget, 5, delta);
  const glanceSide = Math.floor(idleSeconds / 72) % 2 === 0 ? 1 : -1;
  glanceBlend = THREE.MathUtils.damp(glanceBlend, waiting ? idlePulse(4, 5) * glanceSide : 0, 4, delta);
  stretchBlend = THREE.MathUtils.damp(stretchBlend, waiting ? idlePulse(24, 5) : 0, 4, delta);
  postureBlend = THREE.MathUtils.damp(postureBlend, waiting ? idlePulse(67, 4) : 0, 4, delta);
  frontHandsBlend = THREE.MathUtils.damp(frontHandsBlend, waiting ? idleHold(31, 12) : 0, 4, delta);
  backHandsBlend = THREE.MathUtils.damp(backHandsBlend, waiting ? idleHold(57, 9) : 0, 4, delta);
  const speaking = activity === 'SPEAKING' && speech?.mode === 'audio';
  for (const side of [1, -1]) {
    for (const kind of Object.keys(speechPaths)) {
      const target = { lift: 0, travel: 0, accent: 0, wrist: 0, fingers: 0, variant: 0 };
      for (const event of speaking ? speech.gestures || [] : []) {
        if (event.kind !== kind) continue;
        const strength = (event.side === side ? 1 : event.support || 0) * (event.strength ?? 1);
        const delay = event.side === side ? 0 : 0.1;
        const motion = gestureMotion(event, speechSeconds - delay);
        if (motion.lift * strength <= target.lift) continue;
        target.lift = motion.lift * strength;
        target.travel = motion.travel * target.lift;
        target.accent = motion.accent * strength;
        target.wrist = gestureMotion(event, speechSeconds - delay - 0.08).lift * strength;
        target.fingers = gestureMotion(event, speechSeconds - delay - 0.14).lift * strength;
        target.variant = event.variant || 0;
      }
      const id = `${side}:${kind}`;
      const current = speechMotion.get(id) || { lift: 0, travel: 0, accent: 0, wrist: 0, fingers: 0 };
      speechMotion.set(id, dampMotion(current, target, delta, speaking && Boolean(speech.gestures?.length)));
    }
  }
  let gestureTurn = 0;
  let gestureLean = 0;
  let gestureNod = 0;
  for (const [id, motion] of speechMotion) {
    const side = Number(id.split(':')[0]);
    gestureTurn += side * motion.lift * 0.018;
    gestureLean += motion.lift * 0.008;
    gestureNod += motion.accent * (id.endsWith(':emphasis') ? 0.035 : 0.014);
  }
  for (const { bone, rest } of movingBones) bone.quaternion.copy(rest);
  for (const arm of gestureArms) {
    arm.upper.quaternion.copy(arm.upperRest);
    arm.lower.quaternion.copy(arm.lowerRest);
    arm.hand.quaternion.copy(arm.handRest);
    for (const finger of arm.fingers) finger.bone.quaternion.copy(finger.rest);
  }
  if (bodyRoot && stanceLegs.length === 2) {
    bodyRoot.position.copy(rootRest);
    const pelvis = avatar.getObjectByName('Bip01_Pelvis');
    pelvis.quaternion.copy(pelvisRest);
    for (const leg of stanceLegs) {
      leg.upper.quaternion.copy(leg.upperRest);
      leg.lower.quaternion.copy(leg.lowerRest);
      leg.hand.quaternion.copy(leg.footRest);
    }
    avatar.updateMatrixWorld(true);
    const stance = stanceMotion(stanceSeconds, stanceBlend,
      stepping ? stanceSeconds - stepStarted : -1, stepSide);
    const rootWorld = bodyRoot.getWorldPosition(new THREE.Vector3())
      .add(new THREE.Vector3(stance.hipX, stance.hipY, 0));
    bodyRoot.position.copy(bodyRoot.parent.worldToLocal(rootWorld));
    avatar.updateMatrixWorld(true);
    rotateWorld(pelvis, new THREE.Vector3(0, 0, 1), stance.hipRoll);
    for (const leg of stanceLegs) {
      const target = leg.footPosition.clone();
      const moving = stepping && leg.side === stepSide;
      if (moving) target.add(new THREE.Vector3(stance.footX, stance.footLift, stance.footZ));
      poseLimbAtTarget(leg, target, 1, leg.pole, 0.000001);
      const world = leg.footWorld.clone();
      if (moving) world.premultiply(new THREE.Quaternion().setFromAxisAngle(
        new THREE.Vector3(0, 1, 0), stance.footYaw));
      leg.hand.quaternion.copy(leg.hand.parent.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(world));
      leg.hand.updateWorldMatrix(false, true);
    }
  }
  avatar.updateMatrixWorld(true);
  const breath = Math.sin(time * 1.45);
  const talkSway = speakingSway(time, speakingBlend);
  const sway = waitingBlend * Math.sin(time * 0.24) * 0.008 + settlingSway + talkSway.lateral;
  for (const { bone } of movingBones) {
    if (bone.name === 'Bip01_Head') {
      rotateWorld(bone, new THREE.Vector3(0, 1, 0), waitingBlend * Math.sin(time * 0.48) * 0.055 - gestureTurn * 0.6);
      rotateWorld(bone, new THREE.Vector3(1, 0, 0),
        listeningBlend * 0.025 + gestureNod + wristBlend * 0.3 - gestureLean * 0.5 - talkSway.forward * 0.6);
      rotateWorld(bone, new THREE.Vector3(0, 1, 0), wristBlend * 0.12);
      rotateWorld(bone, new THREE.Vector3(0, 1, 0), glanceBlend * 0.2);
      rotateWorld(bone, new THREE.Vector3(1, 0, 0), -stretchBlend * 0.04);
      rotateWorld(bone, new THREE.Vector3(0, 0, 1), Math.sin(time * 0.37) * 0.01 - sway * 0.65);
    } else {
      rotateWorld(bone, new THREE.Vector3(0, 0, 1), sway * (bone.name === 'Bip01_Spine1' ? 0.75 : -0.1));
      rotateWorld(bone, new THREE.Vector3(1, 0, 0), breath * 0.012);
      rotateWorld(bone, new THREE.Vector3(1, 0, 0), -stretchBlend * 0.025 + postureBlend * 0.015);
      rotateWorld(bone, new THREE.Vector3(0, 1, 0), glanceBlend * 0.025 + postureBlend * 0.035);
      rotateWorld(bone, new THREE.Vector3(0, 1, 0),
        gestureTurn * (bone.name === 'Bip01_Spine1' ? 0.7 : 0.3));
      rotateWorld(bone, new THREE.Vector3(1, 0, 0),
        gestureLean + talkSway.forward * (bone.name === 'Bip01_Spine1' ? 0.7 : 0.3));
    }
  }
  for (const arm of gestureArms) {
    let openPalm = 0;
    for (const [kind, path] of Object.entries(speechPaths)) {
      const motion = speechMotion.get(`${arm.side}:${kind}`);
      if (!motion || motion.lift < 0.0001) continue;
      const pelvis = avatar.getObjectByName('Bip01_Pelvis').getWorldPosition(new THREE.Vector3());
      const ready = new THREE.Vector3(...path.ready);
      const end = new THREE.Vector3(...path.end);
      ready.x *= arm.side;
      end.x *= arm.side;
      const variation = ((motion.variant || 0) - 1) * 0.012;
      ready.y += variation;
      end.z += variation;
      const restWrist = arm.hand.getWorldPosition(new THREE.Vector3());
      const target = restWrist.clone().lerp(pelvis.clone().add(ready), motion.lift)
        .addScaledVector(end.sub(ready), motion.travel);
      target.y += Math.sin(Math.PI * motion.travel) * 0.012 * motion.lift;
      const shoulder = arm.upper.getWorldPosition(new THREE.Vector3());
      const pole = arm.lower.getWorldPosition(new THREE.Vector3()).sub(shoulder)
        .addScaledVector(new THREE.Vector3(arm.side * 0.12, 0, -0.08), motion.lift);
      poseLimbAtTarget(arm, target, 1, pole);
      const forward = arm.hand.getWorldPosition(new THREE.Vector3())
        .sub(arm.lower.getWorldPosition(new THREE.Vector3()));
      orientHand(arm, forward, new THREE.Vector3(...path.palm), motion.wrist * 0.8);
      openPalm = Math.max(openPalm, motion.fingers);
    }
    rotateWorld(arm.upper, new THREE.Vector3(1, 0, 0), breath * 0.012);
    rotateWorld(arm.upper, new THREE.Vector3(0, 0, 1), -settlingSway * 0.5);
    aimBone(arm.upper, arm.lower, new THREE.Vector3(arm.side * 0.28, -0.96, -0.12), stretchBlend * 0.65);
    rotateWorld(arm.hand, new THREE.Vector3(0, 1, 0), arm.side * stretchBlend * 0.1);
    if (arm.side === 1) {
      aimBone(arm.upper, arm.lower, new THREE.Vector3(0.25, -0.9, 0.35), wristBlend * 0.8);
      aimBone(arm.lower, arm.hand, new THREE.Vector3(-0.75, 0.45, 0.45), wristBlend);
      orientHand(arm, new THREE.Vector3(-0.9, 0.1, 0.3), new THREE.Vector3(0, -1, 0), wristBlend);
    }
    poseHandsTogether(arm, false, frontHandsBlend);
    poseHandsTogether(arm, true, backHandsBlend);
    const folded = Math.max(frontHandsBlend, backHandsBlend);
    const checking = arm.side === 1 ? wristBlend : 0;
    for (const finger of arm.fingers) {
      const thumb = finger.digit === 0;
      const relaxedCurl = thumb ? 0.025 + folded * 0.07
        : (finger.joint === 0 ? 0.07 : 0.1) * (1 - openPalm * 0.6) + folded * 0.15;
      const fistCurl = thumb ? [0.35, 0.45, 0.3][finger.joint]
        : [0.95, 1.1, 0.65][finger.joint];
      const curl = THREE.MathUtils.lerp(relaxedCurl, fistCurl, checking);
      finger.bone.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(
        new THREE.Vector3(0, 0, 1), curl * (thumb ? 1 : 1 + finger.digit * 0.08)));
    }
  }
}

new FBXLoader(manager).load(`${base}Export/Business_Female_01_facial.fbx`, model => {
  avatar = model;
  const bounds = new THREE.Box3().setFromObject(model);
  const height = bounds.max.y - bounds.min.y;
  if (!Number.isFinite(height) || height <= 0) {
    error.textContent = 'Avatar has invalid bounds.';
    return;
  }
  model.scale.multiplyScalar(1.75 / height);
  const resized = new THREE.Box3().setFromObject(model);
  const center = resized.getCenter(new THREE.Vector3());
  model.position.set(-center.x, -resized.min.y, -center.z);
  model.updateMatrixWorld(true);
  for (const side of ['L', 'R']) {
    const arm = model.getObjectByName(`Bip01_${side}_UpperArm`);
    const elbow = model.getObjectByName(`Bip01_${side}_Forearm`);
    if (!arm || !elbow) {
      error.textContent = 'The resting arm pose could not be applied: arm bones are missing.';
      continue;
    }
    const inverseParent = arm.parent.getWorldQuaternion(new THREE.Quaternion()).invert();
    const current = elbow.getWorldPosition(new THREE.Vector3())
      .sub(arm.getWorldPosition(new THREE.Vector3())).normalize().applyQuaternion(inverseParent);
    const target = new THREE.Vector3(side === 'L' ? 0.14 : -0.14, -1, 0)
      .normalize().applyQuaternion(inverseParent);
    arm.quaternion.premultiply(new THREE.Quaternion().setFromUnitVectors(current, target));
    model.updateMatrixWorld(true);
  }
  model.traverse(object => {
    if (object.isMesh) {
      object.castShadow = true;
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      for (const material of materials) {
        if (material.map) material.map.colorSpace = THREE.SRGBColorSpace;
        material.side = THREE.DoubleSide;
      }
      const dictionary = object.morphTargetDictionary || {};
      const mouth = Object.entries(dictionary).find(([name]) => /AA_VI_10_aa/i.test(name));
      if (mouth) mouths.push({ mesh: object, index: mouth[1] });
      for (const [name, index] of Object.entries(dictionary)) {
        if (/EyeBlinkLeft|EyeBlinkRight/i.test(name)) blinks.push({ mesh: object, index });
      }
    }
    // Lower-body motion is solved separately against world-space foot contacts.
    if (object.isBone && /^(Bip01_Head|Bip01_Spine1|Bip01_Spine2)$/.test(object.name)) {
      movingBones.push({ bone: object, rest: object.quaternion.clone() });
    }
  });
  for (const [label, side] of [['L', 1], ['R', -1]]) {
    const upper = model.getObjectByName(`Bip01_${label}_UpperArm`);
    const lower = model.getObjectByName(`Bip01_${label}_Forearm`);
    const hand = model.getObjectByName(`Bip01_${label}_Hand`);
    if (upper && lower && hand) {
      const fingers = [];
      hand.traverse(bone => {
        const match = bone.name.match(/_Finger([0-4])([12])?$/);
        if (bone.isBone && match) fingers.push({ bone, rest: bone.quaternion.clone(),
          digit: Number(match[1]), joint: Number(match[2] || 0) });
      });
      if (fingers.length !== 15) error.textContent = 'Some finger joints are missing; hand posing may be incomplete.';
      gestureArms.push({ upper, lower, hand, side, upperRest: upper.quaternion.clone(),
        lowerRest: lower.quaternion.clone(), handRest: hand.quaternion.clone(), fingers });
    } else {
      error.textContent = 'Gesture animation unavailable: required arm bones are missing.';
    }
  }
  bodyRoot = model.getObjectByName('Bip01');
  const pelvis = model.getObjectByName('Bip01_Pelvis');
  if (bodyRoot && pelvis) {
    rootRest = bodyRoot.position.clone();
    pelvisRest = pelvis.quaternion.clone();
    for (const [label, side] of [['L', 1], ['R', -1]]) {
      const upper = model.getObjectByName(`Bip01_${label}_Thigh`);
      const lower = model.getObjectByName(`Bip01_${label}_Calf`);
      const foot = model.getObjectByName(`Bip01_${label}_Foot`);
      if (upper && lower && foot) {
        const hip = upper.getWorldPosition(new THREE.Vector3());
        const ankle = foot.getWorldPosition(new THREE.Vector3());
        const axis = ankle.clone().sub(hip).normalize();
        const pole = lower.getWorldPosition(new THREE.Vector3()).sub(hip);
        pole.addScaledVector(axis, -pole.dot(axis));
        // The source pose is almost straight; give each knee a stable forward pole.
        pole.add(new THREE.Vector3(side * 0.04, 0, 1)).normalize();
        stanceLegs.push({ upper, lower, hand: foot, side, pole,
          upperRest: upper.quaternion.clone(), lowerRest: lower.quaternion.clone(),
          footRest: foot.quaternion.clone(), footPosition: ankle,
          footWorld: foot.getWorldQuaternion(new THREE.Quaternion()) });
      }
    }
  }
  if (stanceLegs.length !== 2) error.textContent = 'Lower-body animation unavailable: required leg bones are missing.';
  scene.add(model);
  camera.position.set(0, 1.05, 3.6);
  controls.target.set(0, 0.92, 0);
  controls.update();
  if (!mouths.length || !blinks.length) error.textContent = 'Required speech or blink shapes were not found in the loaded model.';
  text('sara-avatar', mouths.length && blinks.length ? 'Ready' : 'Rig incomplete');
  status.textContent = 'STANDBY';
}, undefined, failure => {
  error.textContent = `Avatar load failed: ${failure.message || String(failure)}`;
  text('sara-avatar', 'Load failed');
});

async function poll() {
  try {
    const response = await fetch('/api/state', { cache: 'no-store' });
    if (!response.ok) throw new Error(`State request failed (${response.status})`);
    snapshot = await response.json();
    receivedAt = performance.now();
    const activity = assistantRunning === false ? 'STANDBY' : snapshot.state === 'PROCESSING' ? 'THINKING' : snapshot.state;
    if (avatar) status.textContent = activity;
    text('sara-activity', activity);
    text('sara-connection', 'Connected');
    text('sara-voice', assistantRunning === false ? 'Idle' : snapshot.speech?.mode === 'audio' ? 'Piper / active' : snapshot.speech?.mode === 'sapi' ? 'SAPI / active' : 'Idle');
    if (error.dataset.connection === 'failed') {
      error.textContent = '';
      delete error.dataset.connection;
    }
  } catch (failure) {
    snapshot = null;
    text('sara-connection', 'Disconnected');
    text('sara-activity', 'Unavailable');
    text('sara-voice', 'Unavailable');
    error.dataset.connection = 'failed';
    error.textContent = `Avatar connection lost: ${failure.message}`;
  }
  setTimeout(poll, 100);
}
poll();

const percent = value => value == null ? '--' : `${value.toFixed(1)}%`;
async function pollTelemetry() {
  try {
    const response = await fetch('/api/telemetry', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    const data = await response.json();
    assistantRunning = data.sara.running;
    text('ollama-status', data.ollama.online ? 'Online' : 'Offline');
    text('ollama-model', data.ollama.model);
    text('ollama-detail', data.ollama.error || (data.ollama.available ? 'Selected model installed' : 'Selected model not installed'));
    document.getElementById('ollama-status').classList.toggle('warning', !data.ollama.online);
    text('sara-process', data.sara.running ? 'Running' : 'Not running');
    text('sara-cpu', percent(data.sara.cpu_percent));
    text('sara-memory', data.sara.memory_mb == null ? '--' : `${data.sara.memory_mb.toFixed(0)} MB`);
    const seconds = data.sara.uptime;
    text('sara-uptime', seconds == null ? '--' : `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m ${Math.floor(seconds % 60)}s`);
    text('sara-detail', data.sara.error || 'Assistant process only / CPU normalized to system capacity');
    for (const name of ['cpu', 'ram']) {
      text(`${name}-value`, percent(data[name].percent));
      document.getElementById(`${name}-bar`).style.width = `${Math.min(100, Math.max(0, data[name].percent))}%`;
    }
    text('cpu-detail', `${data.cpu.threads} logical processors`);
    text('ram-detail', `${data.ram.used_gb.toFixed(1)} / ${data.ram.total_gb.toFixed(1)} GB in use`);
    const gpu = document.getElementById('gpu-devices');
    gpu.replaceChildren();
    if (data.gpu.error) gpu.textContent = data.gpu.error;
    for (const device of data.gpu.devices) {
      const row = document.createElement('p');
      row.className = 'detail';
      row.textContent = `${device.name} / ${percent(device.percent)} / ${device.temperature} C / ${(device.used_mb / 1024).toFixed(1)} of ${(device.total_mb / 1024).toFixed(1)} GB VRAM`;
      gpu.append(row);
    }
    text('telemetry-status', `LIVE / Updated ${new Date(data.sampled_at * 1000).toLocaleTimeString()}`);
    document.getElementById('telemetry-status').classList.remove('warning');
  } catch (failure) {
    text('telemetry-status', `Telemetry unavailable: ${failure.message}. Readings may be stale.`);
    document.getElementById('telemetry-status').classList.add('warning');
  }
  setTimeout(pollTelemetry, 3000);
}
pollTelemetry();

function renderFrame() {
  const delta = Math.min(clock.getDelta(), 0.1);
  elapsed += delta;
  if (elapsed >= nextBlink) {
    blinkStarted = elapsed;
    nextBlink = elapsed + 3 + Math.random() * 3;
  }
  const blink = Math.max(0, 1 - Math.abs((elapsed - blinkStarted) / 0.09 - 1));
  for (const { mesh, index } of blinks) mesh.morphTargetInfluences[index] = blink;
  const speech = snapshot?.speech;
  let opening = 0;
  if (assistantRunning !== false && snapshot?.state === 'SPEAKING' && speech?.mode === 'audio') {
    const now = snapshot.server_time + (performance.now() - receivedAt) / 1000;
    const frame = Math.floor((now - speech.started_at) / speech.step);
    opening = speech.levels[frame] || 0;
  }
  for (const { mesh, index } of mouths) {
    mesh.morphTargetInfluences[index] = THREE.MathUtils.damp(mesh.morphTargetInfluences[index], opening * 0.75, 22, delta);
  }
  animateBody(delta, assistantRunning === false ? 'STANDBY' : snapshot?.state);
  controls.update();
  renderer.render(scene, camera);
}

let scheduledFrame;
let timerScheduled = false;
function scheduleFrame() {
  timerScheduled = document.hidden;
  scheduledFrame = timerScheduled
    ? setTimeout(tick, 50)
    : requestAnimationFrame(tick);
}
function tick() {
  renderFrame();
  scheduleFrame();
}
addEventListener('visibilitychange', () => {
  if (timerScheduled) clearTimeout(scheduledFrame);
  else cancelAnimationFrame(scheduledFrame);
  scheduleFrame();
});
scheduleFrame();
addEventListener('resize', () => {
  camera.aspect = stage.clientWidth / stage.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(stage.clientWidth, stage.clientHeight);
});
