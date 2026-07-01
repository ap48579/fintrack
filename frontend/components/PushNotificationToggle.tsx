"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import { getExistingSubscription, subscribeToPush, unsubscribeFromPush } from "@/lib/push";

export function PushNotificationToggle() {
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);

  useEffect(() => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setSupported(false);
      setSubscribed(false);
      return;
    }
    getExistingSubscription()
      .then((sub) => setSubscribed(sub !== null))
      .catch(() => setSubscribed(false));
  }, []);

  async function enable() {
    setError(null);
    try {
      const { public_key } = await api.getVapidPublicKey();
      if (!public_key) {
        setError("Push isn't configured on the server yet.");
        return;
      }
      const sub = await subscribeToPush(public_key);
      await api.subscribePush(sub.toJSON() as PushSubscriptionJSON);
      setSubscribed(true);
    } catch {
      setError("Could not enable push notifications — check browser permissions.");
    }
  }

  async function disable() {
    const sub = await getExistingSubscription();
    if (sub) {
      await api.unsubscribePush(sub.endpoint);
      await unsubscribeFromPush(sub);
    }
    setSubscribed(false);
  }

  if (!supported) {
    return <p className="text-sm text-gray-500">Push notifications aren&apos;t supported in this browser.</p>;
  }

  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-4">
      <div>
        <div className="text-sm font-medium text-gray-900">Push Notifications</div>
        <div className="text-xs text-gray-500">
          {subscribed ? "Enabled on this device" : "Get a notification when an alert fires"}
        </div>
        {error && <div className="text-xs text-loss">{error}</div>}
      </div>
      <button
        onClick={subscribed ? disable : enable}
        disabled={subscribed === null}
        className={`rounded-full px-3 py-1.5 text-sm font-semibold disabled:opacity-50 ${
          subscribed ? "bg-brand-light text-brand" : "bg-brand text-white hover:bg-brand-dark"
        }`}
      >
        {subscribed ? "Disable" : "Enable"}
      </button>
    </div>
  );
}
