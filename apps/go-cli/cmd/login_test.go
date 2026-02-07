package cmd

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"testing"
)

type fakeFCMClient struct {
	token string
	err   error
}

func (f fakeFCMClient) Register(context.Context) (string, error) {
	return f.token, f.err
}

type fakePNSUpdater struct {
	lastToken string
	calls     int
	err       error
}

func (f *fakePNSUpdater) UpdatePnsHandle(_ context.Context, token string) error {
	f.calls++
	f.lastToken = token
	return f.err
}

func TestRegisterFCMForLogin(t *testing.T) {
	tests := []struct {
		name             string
		useYAML          bool
		fcmToken         string
		fcmErr           error
		updateErr        error
		wantStderrSubstr []string
		wantStdoutSubstr []string
		wantUpdateCalls  int
	}{
		{
			name:    "warn and continue when fcm registration fails",
			useYAML: false,
			fcmErr:  errors.New("fcm boom"),
			wantStderrSubstr: []string{
				"Warning: FCM registration failed: fcm boom",
				"Push notifications will not work. SignalR real-time still available.",
			},
			wantUpdateCalls: 0,
		},
		{
			name:      "warn when pns update fails",
			useYAML:   false,
			fcmToken:  "fcm-token-123",
			updateErr: errors.New("patch failed"),
			wantStderrSubstr: []string{
				"Warning: Failed to update push notification token: patch failed",
			},
			wantUpdateCalls: 1,
		},
		{
			name:     "print success in text mode",
			useYAML:  false,
			fcmToken: "fcm-token-abc",
			wantStdoutSubstr: []string{
				"FCM push notifications registered.",
			},
			wantUpdateCalls: 1,
		},
		{
			name:            "suppress success print in yaml mode",
			useYAML:         true,
			fcmToken:        "fcm-token-yaml",
			wantUpdateCalls: 1,
		},
	}

	origFactory := newLoginFCMClient
	defer func() { newLoginFCMClient = origFactory }()

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			auth := &fakePNSUpdater{err: tc.updateErr}
			newLoginFCMClient = func(sessionDir string) loginFCMClient {
				if sessionDir != "/tmp/session" {
					t.Fatalf("unexpected session dir: %s", sessionDir)
				}
				return fakeFCMClient{token: tc.fcmToken, err: tc.fcmErr}
			}

			var stdout bytes.Buffer
			var stderr bytes.Buffer
			registerFCMForLogin(context.Background(), auth, "/tmp/session", tc.useYAML, &stdout, &stderr)

			if auth.calls != tc.wantUpdateCalls {
				t.Fatalf("update calls: got %d, want %d", auth.calls, tc.wantUpdateCalls)
			}
			if tc.wantUpdateCalls > 0 && auth.lastToken != tc.fcmToken {
				t.Fatalf("update token: got %q, want %q", auth.lastToken, tc.fcmToken)
			}
			for _, sub := range tc.wantStderrSubstr {
				if !strings.Contains(stderr.String(), sub) {
					t.Fatalf("stderr %q does not contain %q", stderr.String(), sub)
				}
			}
			for _, sub := range tc.wantStdoutSubstr {
				if !strings.Contains(stdout.String(), sub) {
					t.Fatalf("stdout %q does not contain %q", stdout.String(), sub)
				}
			}
		})
	}
}
