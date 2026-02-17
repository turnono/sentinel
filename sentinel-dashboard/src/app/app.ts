import { Component, OnInit, OnDestroy } from '@angular/core';
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

  constructor(private sentinelService: SentinelService) { }

  ngOnInit() {
    this.refreshData();
    this.pollingInterval = setInterval(() => this.refreshData(), 2000);
  }

  ngOnDestroy() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
    }
  }

  refreshData() {
    this.sentinelService.checkHealth().subscribe(online => this.isOnline = online);

    if (this.isOnline) {
      this.sentinelService.getPendingRequests().subscribe(reqs => this.pendingRequests = reqs);
      this.sentinelService.getAuditLogs().subscribe(logs => this.auditLogs = logs);
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
