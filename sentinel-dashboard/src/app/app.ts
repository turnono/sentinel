import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SentinelService, PendingRequest, AuditLog } from './sentinel.service';
import { HttpClientModule } from '@angular/common/http';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, HttpClientModule],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class AppComponent implements OnInit, OnDestroy {
  isOnline = false;
  pendingRequests: PendingRequest[] = [];
  auditLogs: AuditLog[] = [];
  pollingInterval: any;

  constructor(private sentinelService: SentinelService, private cdr: ChangeDetectorRef) { }

  ngOnInit() {
    this.refreshData();
    // Increase polling to 5s to reduce log spam
    this.pollingInterval = setInterval(() => this.refreshData(), 5000);
  }

  ngOnDestroy() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
    }
  }

  authError = false;

  refreshData() {
    console.log('Refreshing data... checking health');
    this.sentinelService.checkHealth().subscribe(online => {
      console.log('Health check result:', online);
      this.isOnline = online;

      if (this.isOnline) {
        console.log('System online, fetching pending requests...');
        this.sentinelService.getPendingRequests().subscribe({
          next: (reqs) => {
            console.log('Pending requests fetched:', reqs);
            this.pendingRequests = reqs;
            this.authError = false;
            this.cdr.detectChanges(); // Force UI update
          },
          error: (err) => {
            console.error('Error fetching pending requests:', err);
            this.handleAuthError(err);
            this.cdr.detectChanges();
          }
        });

        if (!this.authError) {
          this.sentinelService.getAuditLogs().subscribe(logs => {
            this.auditLogs = logs;
            this.cdr.detectChanges();
          });
        }
      } else {
        console.warn('System reported offline');
      }
      this.cdr.detectChanges(); // Force UI update for online status
    });
  }

  handleAuthError(err: any) {
    if (err.status === 401) {
      this.authError = true;
      // Only prompt if we haven't given up (simple logic: if we just loaded, prompt. If it fails, show button)
      if (!sessionStorage.getItem('auth_prompt_shown')) {
        sessionStorage.setItem('auth_prompt_shown', 'true');
        setTimeout(() => this.promptForToken(), 100);
      }
    } else {
      console.error("API Error:", err);
    }
  }

  promptForToken() {
    const token = prompt("Enter Sentinel Auth Token (check .env):")?.trim();
    if (token) {
      localStorage.setItem('sentinel_token', token);
      this.authError = false;
      this.refreshData();
    }
  }

  approve(id: string) {
    this.sentinelService.approveRequest(id).subscribe({
      next: () => this.refreshData(),
      error: (err) => {
        if (err.status === 401) {
          const token = prompt("Enter Sentinel Auth Token:");
          if (token) {
            localStorage.setItem('sentinel_token', token);
            this.approve(id); // Retry
          }
        } else {
          alert(`Error: ${err.error?.detail || err.message}`);
        }
      }
    });
  }

  deny(id: string) {
    if (confirm("Reject this request?")) {
      // Optimistic update for now as we lack a specific deny endpoint
      this.pendingRequests = this.pendingRequests.filter(r => r.id !== id);
    }
  }
}
