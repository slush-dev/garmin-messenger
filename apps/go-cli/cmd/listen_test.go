package cmd

import "testing"

func TestListenCommandNoCatchupFlag(t *testing.T) {
	flag := listenCmd.Flags().Lookup("no-catchup")
	if flag == nil {
		t.Fatalf("expected --no-catchup flag to be registered")
	}

	noCatchup, err := listenCmd.Flags().GetBool("no-catchup")
	if err != nil {
		t.Fatalf("GetBool(no-catchup) returned error: %v", err)
	}
	if noCatchup {
		t.Fatalf("expected --no-catchup default to false")
	}
}

func TestMessageDeduper(t *testing.T) {
	isDuplicate, clear := newMessageDeduper()

	if isDuplicate("msg-1") {
		t.Fatalf("first message id should not be duplicate")
	}
	if !isDuplicate("msg-1") {
		t.Fatalf("second message id should be duplicate")
	}

	clear()

	if isDuplicate("msg-1") {
		t.Fatalf("message id should be new again after clear")
	}
}
