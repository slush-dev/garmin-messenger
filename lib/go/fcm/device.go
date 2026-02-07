package fcm

// AndroidDeviceInfo contains device identity information required for
// Android-native GCM/FCM registration, mimicking a real Android device.
type AndroidDeviceInfo struct {
	// BuildFingerprint is the Android build fingerprint
	// Format: brand/product/device:version/build_id/build_number:user/release-keys
	BuildFingerprint string

	// SDKVersion is the Android SDK version (e.g., 33 for Android 13)
	SDKVersion int

	// GMSVersion is the Google Mobile Services (Google Play Services) version
	GMSVersion int

	// Device is the device codename (e.g., "panther" for Pixel 7)
	Device string

	// Model is the device model name (e.g., "Pixel 7")
	Model string

	// ChromeVersion is the Chrome browser version (for compatibility)
	ChromeVersion string
}

// DefaultAndroidDevice returns a credible Pixel 7 device configuration
// based on real Google factory images and Play Services versions.
//
// This configuration is used for Android-native GCM/FCM registration to
// match what a real Android device would send.
func DefaultAndroidDevice() AndroidDeviceInfo {
	return AndroidDeviceInfo{
		// Pixel 7 (panther) build fingerprint from Google factory image
		// Source: https://developers.google.com/android/images
		// Build: TQ3A.230805.001 (August 2023, Android 13)
		BuildFingerprint: "google/panther/panther:13/TQ3A.230805.001/10316531:user/release-keys",

		// Android 13 = SDK 33
		SDKVersion: 33,

		// Google Play Services version 241516037
		// Source: APKMirror (real version from ~August 2023)
		GMSVersion: 241516037,

		// Pixel 7 device info
		Device: "panther",
		Model:  "Pixel 7",

		// Chrome 120.0.6099.144 (stable version from ~December 2023)
		ChromeVersion: "120.0.6099.144",
	}
}
