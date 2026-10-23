import type { CapacitorConfig } from "@capacitor/cli";

// Debug test builds may talk to an EZO server on the home/office LAN over plain HTTP
// (EZO_ANDROID_ALLOW_LAN_HTTP=1 at `cap sync` time). Release builds never set it.
const allowLanHttp = process.env.EZO_ANDROID_ALLOW_LAN_HTTP === "1";

const config: CapacitorConfig = {
  appId: "uz.ezo.mobile",
  appName: "EZO",
  webDir: "dist",
  android: {
    // The app runs at https://localhost: add that origin to the API's EZO_CORS_ORIGINS.
    allowMixedContent: allowLanHttp,
  },
};

export default config;
